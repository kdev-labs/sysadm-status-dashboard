from flask import Flask, render_template, redirect, url_for
from database import get_releases, get_playbooks
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def get_dashboard_data():
    """Get all data needed for the dashboard."""
    logger.info("Fetching data from database...")
    playbooks = get_playbooks()
    releases = get_releases()
    all_hosts = set()
    for playbook in playbooks:
        all_hosts.update(playbook.get('hosts', []))
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
