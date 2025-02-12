from flask import Flask, render_template, redirect, url_for
import json
from pathlib import Path
from datetime import datetime
import pytz
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get status directory from environment variable
STATUS_DIR = os.getenv('STATUS_DIR', '/data/status')
RELEASE_DIR = os.getenv('RELEASE_DIR', '/data/releases')

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

def parse_timestamp_from_filename(filename):
    # Extract timestamp from format: binary_YYYYMMDD_HHMMSS_action.json
    parts = filename.split('_')
    if len(parts) >= 3:
        date_str = parts[1]
        time_str = parts[2]
        try:
            # Combine date and time parts: YYYYMMDD_HHMMSS -> YYYY-MM-DD HH:MM:SS
            timestamp_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
            return datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return None

def load_release_statuses():
    status_dir = Path(RELEASE_DIR)
    releases = {}
    
    if not status_dir.exists():
        return []
    
    # First load all latest status files to get current states
    for latest_file in status_dir.glob('*_latest.json'):
        try:
            binary_name = latest_file.name.replace('_latest.json', '')
            with open(latest_file) as f:
                latest_status = json.load(f)
                
            releases[binary_name] = {
                'name': binary_name,
                'current_state': latest_status['current_state'],
                'last_updated': latest_status['last_updated'],
                'last_action': latest_status['last_action'],
                'history': []
            }
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            app.logger.error(f"Error processing latest file {latest_file}: {str(e)}")
            continue
    
    # Then load all action files (release, promote, rollback)
    for action_file in status_dir.glob('*_2*_*.json'):
        if '_latest.json' in action_file.name:
            continue
            
        try:
            # Parse filename parts
            parts = action_file.name.split('_')
            if len(parts) >= 4:
                binary_name = parts[0]
                action = parts[3].replace('.json', '')
                
                if binary_name not in releases:
                    continue  # Skip if we don't have a latest status for this binary
                
                with open(action_file) as f:
                    action_data = json.load(f)
                
                # Use timestamp from filename
                timestamp = parse_timestamp_from_filename(action_file.name)
                if timestamp:
                    local_tz = pytz.timezone(os.getenv('TZ', 'Europe/Amsterdam'))
                    local_time = timestamp.astimezone(local_tz).strftime('%Y-%m-%d %H:%M:%S')
                    
                    releases[binary_name]['history'].append({
                        'timestamp': local_time,
                        'action': action_data['action'],
                        'source_size': action_data.get('details', {}).get('source_size', 0)
                    })
                
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            app.logger.error(f"Error processing action file {action_file}: {str(e)}")
            continue
    
    # Sort history for each binary by timestamp (newest first)
    for release in releases.values():
        release['history'].sort(key=lambda x: x['timestamp'], reverse=True)
    
    return sorted(releases.values(), key=lambda x: x['name'])

def get_dashboard_data():
    """Get all data needed for the dashboard."""
    logger.info("Fetching data from database...")
    playbooks = load_playbook_statuses()
    releases = load_release_statuses()
    all_hosts = set()
    for playbook in playbooks:
        all_hosts.update(playbook['hosts'])
    logger.info(f"Retrieved {len(playbooks)} playbooks and {len(releases)} releases from database")
    return playbooks, releases, sorted(all_hosts)

@app.route('/')
def index():
    """Redirect root to playbooks by default."""
    return redirect(url_for('playbooks'))

@app.route('/playbooks')
def playbooks():
    """Show playbooks tab."""
    playbooks, releases, hosts = get_dashboard_data()
    return render_template('dashboard.html',
                         active_tab='playbooks',
                         playbooks=playbooks,
                         releases=releases,
                         hosts=hosts)

@app.route('/releases')
def releases():
    """Show releases tab."""
    playbooks, releases, hosts = get_dashboard_data()
    return render_template('dashboard.html',
                         active_tab='releases',
                         playbooks=playbooks,
                         releases=releases,
                         hosts=hosts)

@app.route('/hosts')
def hosts():
    """Show hosts tab."""
    playbooks, releases, hosts = get_dashboard_data()
    return render_template('dashboard.html',
                         active_tab='hosts',
                         playbooks=playbooks,
                         releases=releases,
                         hosts=hosts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
