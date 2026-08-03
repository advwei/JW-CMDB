# CMDB IPAM Agent

Host scanning agent + Asset-IPAM sync service, deployed on Linux hosts.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Linux Host                            │
│                                                         │
│  cmdb_agent (OneAgent)          ipam_sync               │
│  ┌─────────────────────┐   ┌──────────────────────┐    │
│  │ • Local interface IP │   │ • Polls vmserver     │    │
│  │ • Subnet ping-sweep  │   │   assets             │    │
│  │   (reports online +  │   │ • Syncs private_ip   │    │
│  │    offline IPs)      │   │   to IPAM as "used"  │    │
│  │ • Polls tasks via    │   │ • Syncs assetname    │    │
│  │   GET /adt/sync      │   │   as IP description  │    │
│  │ • Reports results via│   └──────────┬───────────┘    │
│  │   POST /history/scan │              │                │
│  └──────────┬──────────┘              │                │
│             │                         │                │
│             └─────────┬───────────────┘                │
│                       │                                │
│              CMDB API (HTTP)                           │
│                       │                                │
└───────────────────────┼────────────────────────────────┘
                        │
              ┌─────────┴──────────┐
              │   Docker Network   │
              │  cmdb-api:5000     │
              │  cmdb-ui:80        │
              └────────────────────┘
```

**Two agents with separate responsibilities:**

| Agent | Responsibility | Online Status Impact |
|-------|---------------|---------------------|
| `cmdb_agent.py` | Host IP reporting + Subnet ping scan | Scan results determine `is_used` (online/offline) |
| `ipam_sync.py` | Asset IP sync + HTTP on-demand scan server | Sets `is_used=1` (online) and `assign_status=0` (assigned), **does not mark offline** |

**Online status rules:**
- **Online**: Detected alive by ping scan, or marked by asset sync
- **Offline**: Only marked by ping scan when host is unreachable
- Asset sync (vmserver etc.) **does not clear** ping scan online status

---

## Directory Structure

All files are installed to `/opt/cmdb-agent/`:

```
/opt/cmdb-agent/
├── cmdb_agent.py          # OneAgent: host scan + subnet scan
├── ipam_sync.py           # Asset-IPAM sync + HTTP scan server
├── config.json            # Configuration file
├── data/                  # State data (agent_id, last_scan, etc.)
└── logs/                  # Log files
    ├── cmdb_agent.log
    └── ipam_sync.log
```

---

## File Inventory

| File | Description |
|------|-------------|
| `cmdb_agent.py` | OneAgent: host interface scan + subnet ping-sweep scanner |
| `ipam_sync.py` | Asset-IPAM sync + HTTP scan server (port 8900) |
| `cmdb-agent.service` | systemd service unit for cmdb_agent |
| `cmdb-agent-ipam-sync.service` | systemd service unit for ipam_sync |
| `install.sh` | One-click installation script |
| `update.sh` | One-click update script |
| `uninstall.sh` | One-click uninstall script |
| `config.json.example` | Configuration file template |

---

## Installation

### One-Click Install

```bash
sudo bash install.sh
```

Installation process:
1. Checks Python3 + requests
2. Checks/installs nmap (optional, recommended)
3. Interactive prompts for CMDB API URL, Key, Secret
4. Auto-generates Agent ID (based on hostname hash)
5. Registers two systemd services and starts them
6. Tests API connectivity

### Update

```bash
sudo bash update.sh
```

### Uninstall

```bash
sudo bash uninstall.sh
```

---

## Configuration

`/opt/cmdb-agent/config.json`:

```json
{
    "cmdb_url": "http://192.168.1.100:8000",
    "api_key": "your_api_key",
    "api_secret": "your_api_secret",
    "agent_id": "0xabcd1234",
    "interval": 7200,
    "log_level": "INFO",
    "skip_interfaces": ["lo", "docker*", "veth*", "br-*", "tun*", "virbr*"],
    "scan_method": "auto",
    "scan_concurrency": 50,
    "ping_timeout": 2,
    "subnet_scan_interval": 7200,
    "asset_types": ["vmserver", "server", "container"],
    "ip_fields": ["private_ip", "public_ip", "ip"],
    "name_fields": ["assetname", "hostname", "name"],
    "subnet_field": "subnet",
    "auth_token": "",
    "http_port": 8900,
    "http_host": "0.0.0.0"
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `cmdb_url` | — | CMDB API address (required) |
| `api_key` | — | API authentication Key (required) |
| `api_secret` | — | API authentication Secret (required) |
| `agent_id` | `0x`+hostname hash | Unique agent identifier, used when creating subnets |
| `interval` | `7200` | Main loop interval (seconds), recommended >= 3600 |
| `log_level` | `INFO` | Log level: DEBUG/INFO/WARNING/ERROR |
| `skip_interfaces` | `["lo","docker*",...]` | Interfaces to skip during local scan |
| `scan_method` | `auto` | Scan method: auto/nmap/fping/arp-scan/ping |
| `scan_concurrency` | `50` | nmap parallelism |
| `ping_timeout` | `2` | Ping timeout (seconds) |
| `subnet_scan_interval` | `7200` | Minimum subnet scan interval (seconds) |
| `asset_types` | `["vmserver","server","container"]` | Asset types monitored by ipam_sync |
| `ip_fields` | `["private_ip","public_ip","ip"]` | IP field names in assets |
| `name_fields` | `["assetname","hostname","name"]` | Name field names in assets |
| `subnet_field` | `subnet` | Subnet reference field in assets |
| `auth_token` | `""` | HTTP scan server auth token (generated via UI Config Center) |
| `http_port` | `8900` | HTTP scan server listen port |
| `http_host` | `0.0.0.0` | HTTP scan server listen address |

---

## Service Management

### systemd

```bash
systemctl start   cmdb-agent              # Start scan agent
systemctl stop    cmdb-agent              # Stop
systemctl restart cmdb-agent              # Restart
systemctl status  cmdb-agent              # Status

systemctl start   cmdb-agent-ipam-sync    # Start asset sync
systemctl stop    cmdb-agent-ipam-sync    # Stop
systemctl restart cmdb-agent-ipam-sync    # Restart
systemctl status  cmdb-agent-ipam-sync    # Status
```

### Manual Execution

```bash
# Run one complete scan cycle (host IP + subnet scan)
sudo /opt/cmdb-agent/cmdb_agent.py --once

# Manually scan a specific subnet
sudo /opt/cmdb-agent/cmdb_agent.py --scan-subnet 10.54.1.0/24

# Validate configuration
sudo /opt/cmdb-agent/cmdb_agent.py --validate

# Run one asset sync cycle
sudo /opt/cmdb-agent/ipam_sync.py --once

# Sync only a specific type
sudo /opt/cmdb-agent/ipam_sync.py --sync-type vmserver

# Validate configuration
sudo /opt/cmdb-agent/ipam_sync.py --validate
```

### Logs

```bash
journalctl -u cmdb-agent -f              # Real-time agent logs
journalctl -u cmdb-agent-ipam-sync -f    # Real-time sync logs
tail -f /opt/cmdb-agent/logs/cmdb_agent.log
tail -f /opt/cmdb-agent/logs/ipam_sync.log
```

---

## Core Features

### 1. Host IP Reporting (cmdb_agent)

Every `interval` seconds (default 7200), scans all non-virtual network interfaces:
- Reads `/sys/class/net/*/address` for MAC addresses
- Runs `ip -o addr show` to get IPs
- Automatically skips lo/docker/veth/br-/tun/virbr virtual interfaces
- Reports via `POST /api/v0.1/ipam/history/scan`
- Sets `is_used=true`, `assign_status=0` (assigned/used)

### 2. Subnet Ping-Sweep Scan (cmdb_agent)

**Workflow:**

```
CMDB UI creates subnet -> specifies Agent ID -> Agent polls tasks -> scans -> reports online+offline IPs
```

**Detailed Steps:**

1. **Create subnet in CMDB UI**: Go to IPAM -> Subnet Management -> Add Subnet
   - CIDR: `10.XX.X.0/24` (example)
   - Scan Agent ID: `0xabcd1234` (must match `agent_id` in config.json)
   - Enable scanning: check

2. **Agent polls tasks**: `GET /api/v0.1/adt/sync?oneagent_id=0xabcd1234`
   ```json
   {
     "subnet_scan_rules": [{
       "ci_id": 123,
       "cidr": "10.X.X.0/24",
       "scan_enabled": true,
       "agent_id": "0xabcd1234",
       "cron": "",
       "last_scan_time": null
     }]
   }
   ```

3. **Agent executes scan**: auto-selects best available tool
   - `nmap -sn -n 10.X.X.0/24` (fastest, parallel)
   - `fping -a -g 10.X.X.0/24` (alternative)
   - `arp-scan 10.X.X.0/24` (local L2 alternative)
   - `ping -c 1 -W 2` (fallback, /24 or smaller)

4. **Agent reports online + offline IPs**: `POST /api/v0.1/ipam/history/scan`
   ```json
   {
     "exec_id": "uuid",
     "ci_id": 123,
     "cidr": "10.X.X.0/24",
     "ips": ["10.X.X.1", "10.X.X.10", "10.X.X.100"],
     "offline_ips": ["10.X.X.2", "10.X.X.3", "10.X.X.4"],
     "status": 0,
     "is_used": "1"
   }
   ```

5. **CMDB processes automatically**:
   - Online IPs (`ips`): sets `is_used=1` (online), `assign_status=0` (assigned)
   - Offline IPs (`offline_ips`): sets `is_used=0` (offline), **does not change `assign_status`**
   - Auto-associates with subnet, refreshes subnet counters

**Scan Interval Control:**
- `subnet_scan_interval: 7200` (default 2 hours)
- Each subnet tracked independently
- Same subnet won't re-scan within the interval
- Can also use cron expressions in subnet scan rules for fine-grained control

**Scan Tool Priority:**
| Tool | Speed | Use Case | Install Command |
|------|-------|----------|-----------------|
| `nmap -sn` | Fastest | All subnets (recommended) | `yum install -y nmap` |
| `fping -g` | Very fast | Large subnets (/16+) | `yum install -y fping` |
| `arp-scan` | Fast | Local L2 scanning | `yum install -y arp-scan` |
| `ping` | Slow | Fallback (/24 or smaller) | System built-in |

### 3. Asset-IPAM Sync (ipam_sync)

**Purpose:** When assets (e.g., vmserver) are created, their `private_ip` is automatically marked as used in IPAM.

**Workflow:**
1. Polls CMDB for `vmserver`/`server` asset models (every `interval` seconds)
2. Reads each asset's `private_ip` and `assetname`
3. Finds or creates `ipam_address` records
4. Sets `is_used=true` (online), `assign_status=0` (assigned)
5. Sets `name` field to `assetname`
6. Auto-associates with correct subnet (CIDR matching or `subnet` reference field)

**Note:** Asset sync only marks IPs as online, **does not mark IPs as offline**. Offline status is only determined by ping scan results.

### 4. On-Demand Scan (ipam_sync HTTP Server)

**Purpose:** Operations personnel can trigger a subnet scan from the UI at any time, without waiting for the agent's polling cycle.

**Architecture:**
```
┌─────────────────────────────────────────────┐
│              ipam_sync.py                    │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │ Main loop (sync) │  │ HTTP Server :8900 │  │
│  │ sync_assets()    │  │ POST /scan       │  │
│  └─────────────────┘  └────────┬─────────┘  │
│                                │             │
│                         daemon thread        │
└────────────────────────────────┼─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │ ThreadPoolExecutor(20)    │
                    │ ping -c 1 -W 1 (concurrent)│
                    └──────────────────────────┘
```

**Workflow:**
1. CMDB UI right-click subnet -> "Scan Subnet"
2. CMDB API -> `POST /ipam/subnet/{id}/scan` -> looks up Agent address -> `POST http://agent:8900/scan`
3. Agent HTTP receives request, validates `X-Auth-Token`, starts background thread
4. Background thread uses `ipaddress.ip_network(cidr)` to expand all host IPs
5. `ThreadPoolExecutor(max_workers=20)` concurrent ping
6. Collects online + offline IPs -> `POST /api/v0.1/ipam/history/scan` report

**Report data example:**
```json
{
  "exec_id": "uuid",
  "ci_id": 123,
  "cidr": "10.X.X.0/24",
  "ips": ["10.X.X.1", "10.X.X.10"],
  "offline_ips": ["10.X.X.2", "10.X.X.3"],
  "is_used": "1"
}
```

**Auth Config:**
- In CMDB UI -> Config Center -> Agent Config, manage agent list
- Each agent has `host`, `port`, `auth_token`
- Agent reads local `config.json` `auth_token` field at startup
- Token can be auto-generated via the "Generate Token" button in Config Center

---

## Agent Protocol

### Agent -> CMDB Server (HMAC Auth)

| Direction | Method | Path | Purpose |
|-----------|--------|------|---------|
| Agent -> Server | GET | `/api/v0.1/adt/sync` | Poll scan tasks |
| Agent -> Server | POST | `/api/v0.1/ipam/history/scan` | Report scan results (online + offline IPs) |
| Agent -> Server | GET | `/api/v0.1/ci/s` | Query CI |

**Auth:** `_key` + `_secret` HMAC-SHA1
- `_key`: API Key
- `_secret`: sha1(url_path + secret + sorted param values)

**Permissions:** API Key used by agent needs `cmdb_agent` or `admin` role.

### Server -> Agent (Token Auth)

CMDB Server calls Agent's scan service via HTTP:

| Direction | Method | Path | Purpose |
|-----------|--------|------|---------|
| Server -> Agent | GET | `http://agent:8900/health` | Health check |
| Server -> Agent | POST | `http://agent:8900/scan` | Trigger subnet ping scan |

**Auth:** `X-Auth-Token` header
- Token is set per-agent in CMDB UI Config Center
- Agent reads from `/opt/cmdb-agent/config.json` -> `auth_token`
- Mismatched tokens return `401 Unauthorized`

**Scan Flow:**
```
CMDB UI (right-click subnet -> "Scan Subnet")
    | POST /api/v0.1/ipam/subnet/{subnet_id}/scan
CMDB API Server (SubnetScanView -> SubnetManager.trigger_scan)
    | POST http://agent:8900/scan (X-Auth-Token)
Agent HTTP Server (ipam_sync.py embedded, daemon thread, port 8900)
    | background concurrent ping
Agent -> CMDB Server: POST /api/v0.1/ipam/history/scan (report online+offline IPs)
```
