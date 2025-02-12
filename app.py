from flask import Flask, render_template
import json
from pathlib import Path
from datetime import datetime
import pytz
import os

app = Flask(__name__)

# Get status directory from environment variable
STATUS_DIR = os.getenv('STATUS_DIR', '/data/status')

def load_playbook_statuses():
    status_dir = Path(STATUS_DIR)
    playbooks = {}
    
    if not status_dir.exists():
        return []
    
    for status_file in status_dir.glob('*.json'):
        try:
            with open(status_file) as f:
                status = json.load(f)
                timestamp = datetime.fromisoformat(status['timestamp'].replace('Z', '+00:00'))
                local_tz = pytz.timezone(os.getenv('TZ', 'Europe/Amsterdam'))
                local_time = timestamp.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')
                
                playbook_name = status['playbook']
                playbooks[playbook_name] = {
                    'name': playbook_name,
                    'last_run': local_time,
                    'status': status['status'],
                    'hosts': status['hosts'],
                    'details': status.get('details', [])
                }
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            app.logger.error(f"Error processing {status_file}: {str(e)}")
            continue
    
    return sorted(playbooks.values(), key=lambda x: x['name'])

def load_release_statuses():
    status_dir = Path(STATUS_DIR) / 'releases'
    releases = {}
    
    if not status_dir.exists():
        return []
    
    # Load latest status files
    for latest_file in status_dir.glob('*_latest.json'):
        try:
            binary_name = latest_file.name.replace('_latest.json', '')
            with open(latest_file) as f:
                latest_status = json.load(f)
                
            # Find the most recent detailed release file
            release_files = list(status_dir.glob(f'{binary_name}_*_release.json'))
            release_files.sort(reverse=True)
            
            if release_files:
                with open(release_files[0]) as f:
                    detailed_status = json.load(f)
                
                timestamp = datetime.fromisoformat(detailed_status['timestamp'].replace('Z', '+00:00'))
                local_tz = pytz.timezone(os.getenv('TZ', 'Europe/Amsterdam'))
                local_time = timestamp.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')
                
                releases[binary_name] = {
                    'name': binary_name,
                    'last_updated': local_time,
                    'last_action': detailed_status['action'],
                    'current_state': latest_status['current_state'],
                    'details': detailed_status.get('details', {}),
                    'states': detailed_status.get('states', {})
                }
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            app.logger.error(f"Error processing release {latest_file}: {str(e)}")
            continue
    
    return sorted(releases.values(), key=lambda x: x['name'])

@app.route('/')
def dashboard():
    playbooks = load_playbook_statuses()
    releases = load_release_statuses()
    all_hosts = set()
    for playbook in playbooks:
        all_hosts.update(playbook['hosts'])
    
    return render_template('dashboard.html', 
                         playbooks=playbooks,
                         releases=releases,
                         hosts=sorted(all_hosts))
