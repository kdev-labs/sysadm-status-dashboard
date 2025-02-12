import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import os
from pathlib import Path
from database import init_db, insert_release, insert_playbook, process_existing_files, file_exists_in_db

class JsonFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith('.json'):
            file_path = Path(event.src_path)
            
            # Skip temporary files and latest status files
            if file_path.name.startswith('.') or file_path.name.endswith('_latest.json'):
                return
                
            print(f"New file detected: {file_path}")
            
            # Determine file type and check for duplicates
            file_type = 'playbook' if 'playbook' in file_path.name else 'release'
            if not file_exists_in_db(file_path, file_type):
                if file_type == 'playbook':
                    insert_playbook(file_path)
                else:
                    insert_release(file_path)
            else:
                print(f"File already processed: {file_path}")

def start_watcher():
    # Initialize the database
    init_db()
    
    # Process existing files
    process_existing_files()
    
    # Set up paths to watch
    playbooks_dir = os.getenv('PLAYBOOK_DIR', '/data/playbooks')
    releases_dir = os.getenv('RELEASE_DIR', '/data/releases')
    
    # Create an observer and handler
    observer = Observer()
    handler = JsonFileHandler()
    
    # Add watchers for both directories
    for directory in [playbooks_dir, releases_dir]:
        if os.path.exists(directory):
            observer.schedule(handler, directory, recursive=False)
            print(f"Watching directory: {directory}")
    
    # Start the observer
    observer.start()
    print("File watcher started...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("File watcher stopped.")
    
    observer.join()

if __name__ == "__main__":
    start_watcher()
