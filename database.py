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

def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

def init_db():
    """Initialize the database with required tables."""
    logger.info(f"Initializing database at {DATABASE_FILE}")
    conn = get_db_connection()
    c = conn.cursor()
    
    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            binary_name TEXT NOT NULL,
            last_updated DATETIME NOT NULL,
            last_action TEXT NOT NULL,
            hosts TEXT,
            has_current BOOLEAN,
            has_new BOOLEAN,
            has_old BOOLEAN,
            git_tag TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(binary_name)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS release_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            binary_name TEXT NOT NULL,
            timestamp DATETIME NOT NULL,
            action TEXT NOT NULL,
            hosts TEXT,
            source_size INTEGER,
            source_path TEXT,
            operation TEXT,
            git_tag TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (binary_name) REFERENCES releases(binary_name)
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(playbook_name)
        )
    ''')
    
    # Create indexes for better performance
    c.execute('CREATE INDEX IF NOT EXISTS idx_release_history_binary ON release_history(binary_name)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_release_history_timestamp ON release_history(timestamp)')
    
    conn.commit()
    conn.close()

def insert_playbook(file_path):
    """Insert or update a playbook JSON file in the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
            
        conn = get_db_connection()
        c = conn.cursor()
        
        timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
        
        # Use INSERT OR REPLACE to update existing record
        c.execute('''
            INSERT OR REPLACE INTO playbooks (
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
        logger.info(f"Upserted playbook in database: {file_path}")
        conn.close()
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")

def insert_release(file_path):
    """Insert or update a release JSON file in the database."""
    try:
        with open(file_path) as f:
            data = json.load(f)
        
        # Skip if it's a latest status file
        if file_path.name.endswith('_latest.json'):
            return
            
        conn = get_db_connection()
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
        
        # Begin transaction
        c.execute('BEGIN TRANSACTION')
        
        try:
            # Update or insert the current state
            c.execute('''
                INSERT OR REPLACE INTO releases (
                    binary_name, last_updated, last_action, hosts,
                    has_current, has_new, has_old, git_tag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['binary_name'],
                timestamp,
                data['action'],
                json.dumps(data.get('hosts', [])),
                data.get('states', {}).get('current', {}).get('exists', False),
                data.get('states', {}).get('new', {}).get('exists', False),
                data.get('states', {}).get('old', {}).get('exists', False),
                data.get('git_tag')
            ))
            logger.info(f"Inserted release with git_tag: {data.get('git_tag')}")
            
            # Add to history
            c.execute('''
                INSERT INTO release_history (
                    binary_name, timestamp, action, hosts,
                    source_size, source_path, operation, git_tag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['binary_name'],
                timestamp,
                data['action'],
                json.dumps(data.get('hosts', [])),
                data.get('details', {}).get('source_size'),
                data.get('details', {}).get('source_path'),
                data.get('details', {}).get('operation'),
                data.get('git_tag')
            ))
            logger.info(f"Added to history with git_tag: {data.get('git_tag')}")
            
            # Commit transaction
            c.execute('COMMIT')
            logger.info(f"Processed release in database: {file_path}")
            
        except Exception as e:
            c.execute('ROLLBACK')
            raise e
            
        conn.close()
    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")

def get_releases(limit=1000):
    """Get the latest releases from the database."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    releases = {}
    
    # Get all current release states
    c.execute('''
        SELECT * FROM releases 
        ORDER BY binary_name
    ''')
    
    for state in c.fetchall():
        logger.info(f"Release state from DB - binary: {state['binary_name']}, git_tag: {state['git_tag']}")
        releases[state['binary_name']] = {
            'name': state['binary_name'],
            'last_updated': state['last_updated'],
            'last_action': state['last_action'],
            'hosts': json.loads(state['hosts']) if state['hosts'] else [],
            'current_state': {
                'has_current': bool(state['has_current']),
                'has_new': bool(state['has_new']),
                'has_old': bool(state['has_old'])
            },
            'git_tag': state['git_tag'],
            'history': []
        }
    
    # Get history for each binary
    for binary_name in releases:
        c.execute('''
            SELECT * FROM release_history
            WHERE binary_name = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (binary_name, limit))
        
        history_items = []
        for h in c.fetchall():
            logger.info(f"History item from DB - binary: {h['binary_name']}, action: {h['action']}, git_tag: {h['git_tag']}")
            history_items.append({
                'timestamp': h['timestamp'],
                'action': h['action'],
                'hosts': json.loads(h['hosts']) if h['hosts'] else [],
                'source_size': h['source_size'],
                'git_tag': h['git_tag']
            })
        releases[binary_name]['history'] = history_items
    
    conn.close()
    logger.info("Fetched release history from database")
    return sorted(releases.values(), key=lambda x: x['name'])

def get_playbooks(limit=1000):
    """Get the latest playbook runs from the database."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        SELECT * FROM playbooks
        ORDER BY playbook_name
        LIMIT ?
    ''', (limit,))
    
    playbooks = [{
        'name': row['playbook_name'],
        'last_run': row['timestamp'],
        'status': row['status'],
        'hosts': json.loads(row['hosts']),
        'details': json.loads(row['details'])
    } for row in c.fetchall()]
    
    conn.close()
    logger.info("Fetched playbooks from database")
    return playbooks

def file_exists_in_db(file_path, file_type='release'):
    """Check if a file has already been processed."""
    conn = get_db_connection()
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
                    SELECT COUNT(*) FROM release_history 
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
    playbooks_dir = os.getenv('STATUS_DIR', '/data/status')
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
