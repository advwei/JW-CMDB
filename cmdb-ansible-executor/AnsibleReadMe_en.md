# CMDB Ansible Integration

## Architecture

```
Browser → cmdb-ui (container) → cmdb-api (container) → HTTP → Ansible Executor (host) → ansible-playbook → target servers
```

The Ansible Executor runs on the **host machine** (not inside Docker) to obtain the necessary network permissions.

---

## File Inventory

### 1. cmdb-ansible-executor/ (Host Service)

| File | Description |
|------|-------------|
| `app.py` | Flask application entry point, 3 API endpoints + API Key auth |
| `executor.py` | Core logic: dynamic inventory generation → `subprocess.run(["ansible-playbook", ...])` |
| `config.py` | Environment variable configuration (port, paths, timeout) |
| `requirements.txt` | Python dependencies |
| `cmdb-ansible.service` | systemd unit file |

API Endpoints:
- `GET  /api/exec/health` — Health check (no auth)
- `GET  /api/exec/playbooks` — List `.yml`/`.yaml` files from `/opt/ansible/playbooks/`
- `POST /api/exec/run-playbook` — Execute a playbook (requires `X-API-Key` header)

### 2. cmdb-api Backend

| File | Description |
|------|-------------|
| `api/lib/cmdb/ansible.py` | Integration library: `AnsibleClient` + `AnsibleSync`, reads config, fetches CI data, calls Executor |
| `api/views/cmdb/ansible.py` | 4 view classes, auto-registered at `/api/v0.1/ansible/` |

API Endpoints (provided by cmdb-api):

| Route | Method | Description |
|-------|--------|-------------|
| `POST /api/v0.1/ansible/setup-server/<ci_id>` | Single CI initialization |
| `POST /api/v0.1/ansible/setup-server/batch` | Batch initialization |
| `GET  /api/v0.1/ansible/playbooks` | List available playbooks |
| `GET/POST /api/v0.1/ansible/config` | Ansible configuration management |

### 3. cmdb-ui Frontend

| File | Description |
|------|-------------|
| `src/modules/cmdb/api/ansible.js` | Frontend API wrapper |
| `src/modules/cmdb/views/sync_asset/configCenter.vue` | Config Center tabs: **JumpServer** + **Ansible** |
| `src/modules/cmdb/views/ci/instanceList.vue` | Batch action bar "Ansible Init" button |
| `src/modules/cmdb/views/ci/modules/ciDetailTab.vue` | Detail page "Ansible Init" button |

---

## Data Flow

```
1. User opens Config Center → Ansible tab
   → Configures Executor URL, API Key, OS credential mapping, field mapping, default playbook

2. User enters CI list → selects vmserver assets
   → Clicks "Ansible Init" → selects playbook → confirms

3. Frontend POST /api/v0.1/ansible/setup-server/batch
   { ci_ids: [1,2,3], playbook: "setup_server.yml", new_password: "xxx" }

4. cmdb-api processes each CI:
   a. Calls CIManager.get_ci_by_id_from_db() to get CI details
   b. Extracts IP, hostname, os_version based on field_map
   c. Matches OS credentials for port/user/password
   d. POSTs to http://<executor>/api/exec/run-playbook

5. Executor service:
   a. Validates input security
   b. Generates temporary inventory file in /opt/ansible/inventory/
   c. Runs ansible-playbook
   d. Cleans up temporary files
   e. Returns results

6. Frontend displays execution results
```

---

## Deployment

### Prerequisites

- Host has Ansible installed
- Playbook directory: `/opt/ansible/playbooks/`
- Inventory directory: `/opt/ansible/inventory/`

### 1. Deploy Executor

```bash
# Copy cmdb-ansible-executor to host
scp -r cmdb-ansible-executor/ root@your-host:/opt/

# Install dependencies
cd /opt/cmdb-ansible-executor
pip install -r requirements.txt

# Change API Key (use a secure value)
# Edit EXECUTOR_API_KEY in cmdb-ansible.service

# Configure systemd
cp cmdb-ansible.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable cmdb-ansible
systemctl start cmdb-ansible

# Verify
curl http://localhost:18081/api/exec/health
```

### 2. Environment Variables (Executor)

| Variable | Default | Description |
|----------|---------|-------------|
| `EXECUTOR_HOST` | `0.0.0.0` | Listen address |
| `EXECUTOR_PORT` | `18081` | Listen port |
| `EXECUTOR_API_KEY` | `change-me-to-a-secure-key` | API auth key |
| `ANSIBLE_BASE_DIR` | `/opt/ansible` | Ansible base directory |
| `ANSIBLE_TIMEOUT` | `600` | Playbook execution timeout (seconds) |

### 3. Configuration (CMDB UI)

1. Log in to CMDB → Config Center → **Ansible Settings**
2. Fill in **Executor URL** (e.g., `http://192.168.1.100:18081`)
3. Fill in **API Key** (must match cmdb-ansible.service)
4. Configure **OS Credential Mapping**:
   | OS | Port | Username | Password |
   |---------|------|----------|----------|
   | Linux | 22 | root | xxx |

5. Configure **Field Mapping** (CI attribute → Ansible param):
   - IP field: `ip, private_ip, public_ip, address`
   - Hostname field: `hostname, name, assetname`
   - OS field: `os_version, os, ostype, platform`
6. Select **Default Playbook**
7. Click Save

### 4. Usage

- **Batch init**: CI list → check assets → "Ansible Init" → select playbook → confirm
- **Single asset init**: CI detail page → "Ansible Init" → select playbook → confirm

---

## Security

- Executor uses `X-API-Key` header for authentication
- Playbook names validated against regex to prevent path traversal
- Inventory variable values with spaces are JSON-serialized
- Temporary inventory files are deleted immediately after execution
- CI passwords are fetched via `CIManager.load_password()` and never logged

## Windows Support

When Windows playbooks are ready:

1. Place Windows playbooks in `/opt/ansible/playbooks/`
2. Add Windows entries in Config Center OS credential mapping
3. Users select the corresponding Windows playbook during initialization
