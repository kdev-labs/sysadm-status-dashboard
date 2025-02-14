import os
import time
import logging
import hashlib
import json
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from db import execute_query, get_db_connection
from dateutil.parser import isoparse


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FILE_EXISTS = "SELECT 1 FROM file_hashes WHERE file_path = ? AND file_hash = ? LIMIT 1"
INSERT_REPLACE_FILE_HASHES = "INSERT OR REPLACE INTO file_hashes (file_path, file_hash) VALUES (?, ?)"

class JsonFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            file_path = Path(event.src_path)
            
            # Skip temporary files and latest status files
            if file_path.name.startswith('.'):
                return
                
            logger.info(f"New file detected: {file_path}")
            
            # Determine file type and check for duplicates
            if 'playbook' in file_path.name:
                file_type = 'playbook'
            elif any(x in file_path.name for x in ['release', 'promote', 'rollback']):
                file_type = 'release'
            else:
                logger.info(f"Unknown file type: {file_path}")
                return

            # Calculate file hash
            file_hash = compute_file_hash(file_path)
            
            # Process the file based on type
            success = False
            if file_type == 'playbook':
                success = upsert_playbook(file_path)
            elif file_type == 'release':
                success = upsert_release(file_path)
                
            # Only add to file_hashes if processing was successful
            if success:
                execute_query(INSERT_REPLACE_FILE_HASHES, (file_path, file_hash), commit=True)
                logger.info(f"Upserted new file_path file_hash file: {file_path}, {file_hash}")


def start_watcher():
    global playbooks_dir, releases_dir
    # Process existing files to catch up or initialize
    process_existing_files()
    
    # Create an observer and handler
    observer = Observer()
    handler = JsonFileHandler()
    
    # Add watchers for both directories
    for directory in [playbooks_dir, releases_dir]:
        if os.path.exists(directory):
            observer.schedule(handler, directory, recursive=False)
            logger.info(f"Watching directory: {directory}")
    
    # Start the observer
    observer.start()
    logger.info("File watcher started...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("File watcher stopped.")
    
    observer.join()


# This is just for the restart behaviour to not read the same file twice
# Or when we initialize with a new DB and want to catch up
def process_existing_files():
    global playbooks_dir, releases_dir, FILE_EXISTS
    """Process all existing JSON files in the directories."""
    logger.info("Starting to process existing files...")
    
    processed_count = {'playbook': 0, 'release': 0}
    skipped_count = {'playbook': 0, 'release': 0}
    failed_count = {'playbook': 0, 'release': 0}

    for directory, file_type in [(playbooks_dir, 'playbook'), (releases_dir, 'release')]:
        if not os.path.exists(directory):
            logger.warning(f"Directory does not exist: {directory}")
            continue
            
        # Get all JSON files and sort them by creation time
        files = Path(directory).glob('*.json')
        sorted_files = sorted(files, key=lambda x: (x.stat().st_ctime, str(x)))
        
        for file_path in sorted_files:
            # Skip temporary files
            if file_path.name.startswith('.'):
                continue
                
            # Check if file has already been processed
            file_hash = compute_file_hash(file_path)
            exists = execute_query(FILE_EXISTS, (str(file_path), file_hash))
            if exists:
                logger.debug(f"Skipping already processed file: {file_path}")
                skipped_count[file_type] += 1
                continue
                
            # Process the file based on type
            success = False
            if file_type == 'playbook':
                success = upsert_playbook(file_path)
            elif file_type == 'release':
                success = upsert_release(file_path)
                
            if success:
                logger.info(f"Upserted new file_path file_hash file: {file_path}, {file_hash}")
                processed_count[file_type] += 1
                execute_query(INSERT_REPLACE_FILE_HASHES, (str(file_path), file_hash), commit=True)
            else:
                failed_count[file_type] += 1

    logger.info(f"Finished processing existing files:")
    logger.info(f"Processed: {processed_count['playbook']} playbooks, {processed_count['release']} releases")
    logger.info(f"Skipped: {skipped_count['playbook']} playbooks, {skipped_count['release']} releases")
    logger.info(f"Failed: {failed_count['playbook']} playbooks, {failed_count['release']} releases")


def upsert_release(file_path):
    """Insert or update a release JSON file in the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
        
        try:
            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        except Exception as e:
            logger.error(f"Error parsing timestamp with datetime for release {file_path}: {str(e)}")
            try:
                timestamp = isoparse(data['timestamp'])
            except Exception as e:
                logger.error(f"Error parsing timestamp with dateutil for release {file_path}: {str(e)}")
                return False
        
        # Get a single connection for the entire transaction
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Begin transaction
            conn.execute('BEGIN TRANSACTION')
            
            # Update or insert the current state
            hosts_json = json.dumps(data.get('hosts', []))
            logger.info(f"Processing hosts for {data['binary_name']}: {hosts_json}")
            cursor.execute('''
                INSERT OR REPLACE INTO releases (
                    binary_name, last_action, git_tag, last_updated, hosts, has_current, has_new, has_old
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['binary_name'],
                data['action'],
                data.get('git_tag'),
                timestamp,
                hosts_json,
                data['states']['current']['exists'],
                data['states']['new']['exists'],
                data['states']['old']['exists']
            ))
            
            # Add to history
            cursor.execute('''
                INSERT INTO release_history (
                    binary_name, action, git_tag, timestamp, hosts, source_size, source_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['binary_name'],
                data['action'],
                data.get('git_tag'),
                timestamp,
                hosts_json,
                data['details']['source_size'],
                data['details']['source_path']
            ))
            
            logger.info(f"Added to history with git_tag: {data.get('git_tag')}")
            # Commit the transaction
            conn.commit()
            logger.info(f"Processed release in database: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing release {file_path}: {str(e)}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"Error reading release file {file_path}: {str(e)}")
        return False


def upsert_playbook(file_path):
    """Insert or update a playbook JSON file in the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
            
        timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        # Use INSERT OR REPLACE to update existing record
        execute_query('''
            INSERT OR REPLACE INTO playbooks (
                playbook_name, timestamp, status, hosts, details
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            data['playbook'],
            timestamp,
            data['status'],
            json.dumps(data['hosts']),
            json.dumps(data.get('details', []))
        ), commit=True)
        
        logger.info(f"Upserted playbook in database: {file_path}")
    except Exception as e:
        logger.error(f"Error processing playbook {file_path}: {str(e)}")
        return False
    return True



def compute_file_hash(file_path):
    """Compute the hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


if __name__ == "__main__":
    playbooks_dir = os.getenv('STATUS_DIR')
    releases_dir = os.getenv('RELEASE_DIR')
    start_watcher()
