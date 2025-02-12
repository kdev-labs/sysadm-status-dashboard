# Ansible Status Dashboard

A simple dashboard to monitor the status of Ansible playbook executions.

## Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file to match your environment:
   - `DASHBOARD_PORT`: Port to run the dashboard on (default: 5000)
   - `STATUS_FILES_PATH`: Path where Ansible stores status JSON files
   - `RELEASE_FILES_PATH`: Path where Ansible stores release JSON files
   - `TIMEZONE`: Your local timezone

3. Start the dashboard:
   ```bash
   docker-compose up -d
   ```

4. Redeploy the container:
   ```bash
   docker-compose up -d --build
   ```

The dashboard will be available at:
- Locally: `http://localhost:5000` (or whatever port you configured)
- From other machines: `http://<host-ip>:5000`

## Configuration

The dashboard reads JSON status files created by Ansible playbooks. These files should be in the directory specified by `STATUS_FILES_PATH` and `RELEASE_FILES_PATH`.

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| DASHBOARD_PORT | Port to run the dashboard on | 5000 |
| STATUS_FILES_PATH | Path to status JSON files | /var/log/ansible/status |
| RELEASE_FILES_PATH | Path to release JSON files | /var/log/ansible/releases |
| TIMEZONE | Local timezone | Europe/Amsterdam |

## Features

- Shows status of all playbook executions per host
- Color-coded status indicators
- Timezone-aware timestamps
- Accessible from any machine on the network
