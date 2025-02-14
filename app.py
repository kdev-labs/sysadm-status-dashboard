from flask import Flask, g, render_template, redirect, url_for
import logging
from db import get_db
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.teardown_appcontext
def close_db(exception):
    """Close the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def get_playbooks(limit=1000):
    """Get the latest 1k playbook runs from the database."""
    database = get_db()
    result = database.execute("SELECT * FROM playbooks ORDER BY playbook_name LIMIT ?", (limit,)).fetchall()
    playbooks = [{
        'name': row['playbook_name'],
        'last_run': row['timestamp'],
        'status': row['status'],
        'hosts': json.loads(row['hosts']),
        'details': json.loads(row['details'])
    } for row in result]
    logger.info(f"Fetched {len(playbooks)} playbooks from database")
    return playbooks


def get_releases(limit=1000):
    """Get the latest releases from the database."""
    database = get_db()
    releases = {}
    
    # Get all current release states
    logger.info("Fetching current release states...")
    rel = database.execute("SELECT * FROM releases ORDER BY binary_name").fetchall()
    
    for state in rel:
        logger.info(f"Current state for {state['binary_name']}: action={state['last_action']}, git_tag={state['git_tag']}")
        logger.info(f"Hosts for {state['binary_name']}: {state['hosts']}")
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
    logger.info(f"Fetched {len(releases)} releases from database")
    # Get history for each binary
    for binary_name in releases:
        rel_history = database.execute("SELECT * FROM release_history WHERE binary_name = ?  ORDER BY timestamp DESC LIMIT ?  ", (binary_name, limit)).fetchall()
        history_items = []
        for h in rel_history:
            logger.info(f"History item from DB - binary: {h['binary_name']}, action: {h['action']}, git_tag: {h['git_tag']}")
            history_items.append({
                'timestamp': h['timestamp'],
                'action': h['action'],
                'hosts': json.loads(h['hosts']) if h['hosts'] else [],
                'source_size': h['source_size'],
                'git_tag': h['git_tag']
            })
        releases[binary_name]['history'] = history_items
    logger.info("Fetched release history from database")
    return sorted(releases.values(), key=lambda x: x['name'])


def get_hosts():
    database = get_db()
    result = database.execute("SELECT DISTINCT hosts FROM playbooks ORDER BY hosts").fetchall()
    all_hosts = set()
    for row in result:
        all_hosts.update(json.loads(row['hosts']))
    logger.info(f"Fetched hosts from database")
    return sorted(all_hosts)

@app.route('/')
def index():
    """Redirect root to playbooks by default."""
    return redirect(url_for('playbooks'))

@app.route('/playbooks')
def playbooks():
    """Show playbooks tab."""
    playbooks = get_playbooks()
    return render_template('playbooks.html', active_tab='playbooks', playbooks=playbooks)

@app.route('/releases')
def releases():
    """Show releases tab."""
    releases = get_releases()
    return render_template('releases.html', active_tab='releases', releases=releases)

@app.route('/hosts')
def hosts():
    """Show hosts tab."""
    hosts = get_hosts()
    return render_template('hosts.html', active_tab='hosts', hosts=hosts)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
