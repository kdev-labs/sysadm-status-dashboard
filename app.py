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

@app.route('/')
def dashboard():
    playbooks = load_playbook_statuses()
    all_hosts = set()
    for playbook in playbooks:
        all_hosts.update(playbook['hosts'])
    
    return render_template('dashboard.html', 
                         playbooks=playbooks,
                         hosts=sorted(all_hosts))
