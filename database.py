import sqlite3
from datetime import datetime
import json
import os
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_FILE = os.getenv('DATABASE_FILE', '/data/db/dashboard.db')

def init_db():
    """Initialize the database with required tables."""
    logger.info(f"Initializing database at {DATABASE_FILE}")
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    
    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            binary_name TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            action TEXT NOT NULL,
            source_size INTEGER,
            source_path TEXT,
            operation TEXT,
            has_current BOOLEAN,
            has_new BOOLEAN,
            has_old BOOLEAN,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS playbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playbook_name TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            status TEXT NOT NULL,
            hosts TEXT NOT NULL,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def insert_release(file_path):
    """Insert a release JSON file into the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
        
        # Skip if it's a latest status file
        if file_path.name.endswith('_latest.json'):
            return
            
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        
        # Parse timestamp from filename
        parts = file_path.name.split('_')
        if len(parts) >= 3:
            date_str = parts[1]
            time_str = parts[2]
            timestamp_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        else:
            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        
        c.execute('''
            INSERT INTO releases (
                binary_name, timestamp, action, source_size, source_path, operation,
                has_current, has_new, has_old
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['binary_name'],
            timestamp,
            data['action'],
            data.get('details', {}).get('source_size'),
            data.get('details', {}).get('source_path'),
            data.get('details', {}).get('operation'),
            data.get('states', {}).get('current', {}).get('exists', False),
            data.get('states', {}).get('new', {}).get('exists', False),
            data.get('states', {}).get('old', {}).get('exists', False)
        ))
        
        conn.commit()
        logger.info(f"Inserted release into database: {file_path}")
        conn.close()
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")

def insert_playbook(file_path):
    """Insert a playbook JSON file into the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
            
        conn = sqlite3.connect(DATABASE_FILE)
        c = conn.cursor()
        
        timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        
        c.execute('''
            INSERT INTO playbooks (
                playbook_name, timestamp, status, hosts, details
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            data['playbook'],
            timestamp,
            data['status'],
            json.dumps(data['hosts']),
            json.dumps(data.get('details', []))
        ))
        
        conn.commit()
        logger.info(f"Inserted playbook into database: {file_path}")
        conn.close()
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")

def get_releases(limit=1000):
    """Get the latest releases from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    releases = {}
    
    # Get the latest state for each binary
    c.execute('''
        WITH latest_releases AS (
            SELECT binary_name, MAX(timestamp) as max_timestamp
            FROM releases
            GROUP BY binary_name
        )
        SELECT r.*
        FROM releases r
        JOIN latest_releases lr
        ON r.binary_name = lr.binary_name AND r.timestamp = lr.max_timestamp
    ''')
    latest_states = c.fetchall()
    
    for state in latest_states:
        releases[state['binary_name']] = {
            'name': state['binary_name'],
            'last_updated': state['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'last_action': state['action'],
            'current_state': {
                'has_current': bool(state['has_current']),
                'has_new': bool(state['has_new']),
                'has_old': bool(state['has_old'])
            },
            'history': []
        }
    
    # Get history for each binary
    for binary_name in releases:
        c.execute('''
            SELECT * FROM releases
            WHERE binary_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (binary_name, limit))
        history = c.fetchall()
        
        releases[binary_name]['history'] = [{
            'timestamp': h['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'action': h['action'],
            'source_size': h['source_size']
        } for h in history]
    
    conn.close()
    logger.info("Fetched releases from database")
    return sorted(releases.values(), key=lambda x: x['name'])

def get_playbooks(limit=1000):
    """Get the latest playbook runs from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Get the latest run for each playbook
    c.execute('''
        WITH latest_runs AS (
            SELECT playbook_name, MAX(timestamp) as max_timestamp
            FROM playbooks
            GROUP BY playbook_name
        )
        SELECT p.*
        FROM playbooks p
        JOIN latest_runs lr
        ON p.playbook_name = lr.playbook_name AND p.timestamp = lr.max_timestamp
        ORDER BY p.playbook_name
        LIMIT ?
    ''', (limit,))
    
    playbooks = []
    for row in c.fetchall():
        playbooks.append({
            'name': row['playbook_name'],
            'last_run': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'status': row['status'],
            'hosts': json.loads(row['hosts']),
            'details': json.loads(row['details'])
        })
    
    conn.close()
    logger.info("Fetched playbooks from database")
    return playbooks

def file_exists_in_db(file_path, file_type='release'):
    """Check if a file has already been processed."""
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    
    try:
        if file_type == 'release':
            # Extract timestamp from filename for releases
            parts = Path(file_path).name.split('_')
            if len(parts) >= 3:
                date_str = parts[1]
                time_str = parts[2]
                timestamp_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
                binary_name = parts[0]
                
                c.execute('''
                    SELECT COUNT(*) FROM releases 
                    WHERE binary_name = ? AND timestamp = ?
                ''', (binary_name, timestamp_str))
            else:
                return False
        else:
            # For playbooks, check the combination of name and timestamp from the file
            with open(file_path) as f:
                data = json.load(f)
            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            
            c.execute('''
                SELECT COUNT(*) FROM playbooks 
                WHERE playbook_name = ? AND timestamp = ?
            ''', (data['playbook'], timestamp))
        
        count = c.fetchone()[0]
        logger.debug(f"Checked file existence in database: {file_path}, exists={count > 0}")
        return count > 0
    except Exception as e:
        logger.error(f"Error checking file existence: {str(e)}")
        return False
    finally:
        conn.close()

def process_existing_files():
    """Process all existing JSON files in the directories."""
    logger.info("Starting to process existing files...")
    playbooks_dir = os.getenv('PLAYBOOK_DIR', '/data/playbooks')
    releases_dir = os.getenv('RELEASE_DIR', '/data/releases')
    
    processed_count = {'playbook': 0, 'release': 0}
    skipped_count = {'playbook': 0, 'release': 0}
    
    for directory, file_type in [(playbooks_dir, 'playbook'), (releases_dir, 'release')]:
        if not os.path.exists(directory):
            logger.warning(f"Directory does not exist: {directory}")
            continue
            
        for file_path in Path(directory).glob('*.json'):
            # Skip temporary files and latest status files
            if file_path.name.startswith('.') or file_path.name.endswith('_latest.json'):
                continue
                
            # Check if file has already been processed
            if not file_exists_in_db(file_path, file_type):
                logger.info(f"Processing existing file: {file_path}")
                if file_type == 'playbook':
                    insert_playbook(file_path)
                else:
                    insert_release(file_path)
                processed_count[file_type] += 1
            else:
                logger.debug(f"Skipping already processed file: {file_path}")
                skipped_count[file_type] += 1
    
    logger.info(f"Finished processing existing files:")
    logger.info(f"Processed: {processed_count['playbook']} playbooks, {processed_count['release']} releases")
    logger.info(f"Skipped: {skipped_count['playbook']} playbooks, {skipped_count['release']} releases")
