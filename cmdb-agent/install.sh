#!/bin/bash
#
# CMDB IPAM OneAgent & Sync Installer
# Installs:
#   cmdb_agent  - OneAgent: host scanner + subnet ping-sweep scanner
#   ipam_sync   - Asset-IPAM sync + HTTP scan server (port 8900)
#                 receives on-demand scan requests from CMDB UI
#
# Installation directory: /opt/cmdb-agent
#

set -euo pipefail

AGENT_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/cmdb-agent"
CONFIG_FILE="${INSTALL_DIR}/config.json"
DATA_DIR="${INSTALL_DIR}/data"
LOG_DIR="${INSTALL_DIR}/logs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_prerequisites() {
    if ! command -v python3 &>/dev/null; then
        error "Python 3 is not installed. Install with: yum install -y python3"
        exit 1
    fi
    if ! python3 -c "import requests" 2>/dev/null; then
        warn "Python 'requests' module not found, installing..."
        python3 -m pip install requests || {
            error "Failed to install requests"
            exit 1
        }
    fi
    if ! command -v ip &>/dev/null; then
        warn "'ip' command not found, installing iproute2..."
        if command -v yum &>/dev/null; then
            yum install -y iproute
        elif command -v apt-get &>/dev/null; then
            apt-get update && apt-get install -y iproute2
        fi
    fi
}

install_scripts() {
    info "Creating installation directory: ${INSTALL_DIR}"
    mkdir -p "${INSTALL_DIR}" "${DATA_DIR}" "${LOG_DIR}"
    chmod 755 "${INSTALL_DIR}" "${DATA_DIR}" "${LOG_DIR}"

    info "Installing cmdb_agent.py to ${INSTALL_DIR}/"
    cp "${AGENT_SRC_DIR}/cmdb_agent.py" "${INSTALL_DIR}/cmdb_agent.py"
    chmod 755 "${INSTALL_DIR}/cmdb_agent.py"

    info "Installing ipam_sync.py to ${INSTALL_DIR}/"
    cp "${AGENT_SRC_DIR}/ipam_sync.py" "${INSTALL_DIR}/ipam_sync.py"
    chmod 755 "${INSTALL_DIR}/ipam_sync.py"
}

generate_agent_id() {
    local hostname
    hostname=$(hostname)
    echo -n "0x"
    echo -n "$hostname" | sha1sum | cut -c1-6
}

setup_config() {
    local agent_id
    agent_id=$(generate_agent_id)

    if [[ -f "${CONFIG_FILE}" ]]; then
        warn "Config file ${CONFIG_FILE} already exists, skipping"
        info "Agent ID: $(python3 -c "import json; print(json.load(open('${CONFIG_FILE}')).get('agent_id', 'unknown'))")"
        return
    fi

    info "This agent will use ID: ${agent_id}"
    read -r -p "CMDB API URL [http://localhost:8000]: " cmdb_url
    cmdb_url="${cmdb_url:-http://localhost:8000}"

    read -r -p "CMDB API Key: " api_key
    while [[ -z "${api_key}" ]]; do
        error "API Key cannot be empty"
        read -r -p "CMDB API Key: " api_key
    done

    read -r -s -p "CMDB API Secret: " api_secret
    echo
    while [[ -z "${api_secret}" ]]; do
        error "API Secret cannot be empty"
        read -r -s -p "CMDB API Secret: " api_secret
        echo
    done

    cat > "${CONFIG_FILE}" <<EOF
{
    "cmdb_url": "${cmdb_url}",
    "api_key": "${api_key}",
    "api_secret": "${api_secret}",
    "agent_id": "${agent_id}",
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
EOF
    chmod 600 "${CONFIG_FILE}"
    info "Config written to ${CONFIG_FILE}"
    info "Agent ID: ${agent_id}"
    echo ""
    echo "  IMPORTANT: In the CMDB UI, when creating a subnet, set"
    echo "  'Scan Agent ID' to: ${agent_id}"
    echo "  Then this agent will automatically scan that subnet."
    echo ""
    echo "  IMPORTANT: After installation, go to CMDB UI -> Config Center"
    echo "  -> Agent Config to add this agent (host/port/auth_token)."
    echo "  The auth_token must match the 'auth_token' field in config.json"
    echo "  (currently empty -- configure it in both places)."
    echo ""
}

install_services() {
    info "Installing cmdb-agent.service"
    cp "${AGENT_SRC_DIR}/cmdb-agent.service" /etc/systemd/system/cmdb-agent.service
    chmod 644 /etc/systemd/system/cmdb-agent.service

    info "Installing cmdb-agent-ipam-sync.service"
    cp "${AGENT_SRC_DIR}/cmdb-agent-ipam-sync.service" /etc/systemd/system/cmdb-agent-ipam-sync.service
    chmod 644 /etc/systemd/system/cmdb-agent-ipam-sync.service

    systemctl daemon-reload
}

enable_services() {
    info "Enabling services to start on boot"
    systemctl enable cmdb-agent.service 2>/dev/null || warn "systemctl enable cmdb-agent failed (non-systemd?)"
    systemctl enable cmdb-agent-ipam-sync.service 2>/dev/null || warn "systemctl enable cmdb-agent-ipam-sync failed (non-systemd?)"
}

start_services() {
    info "Starting cmdb-agent.service"
    systemctl start cmdb-agent.service 2>/dev/null || {
        warn "Failed to start cmdb-agent (may need systemd)"
        systemctl status cmdb-agent.service --no-pager 2>/dev/null || true
    }
    info "Starting cmdb-agent-ipam-sync.service"
    systemctl start cmdb-agent-ipam-sync.service 2>/dev/null || {
        warn "Failed to start cmdb-agent-ipam-sync (may need systemd)"
        systemctl status cmdb-agent-ipam-sync.service --no-pager 2>/dev/null || true
    }
    sleep 2
    systemctl status cmdb-agent.service --no-pager 2>/dev/null || true
    systemctl status cmdb-agent-ipam-sync.service --no-pager 2>/dev/null || true
}

install_scan_tools() {
    info "Checking for subnet scan tools..."
    local tools_installed=0

    if command -v nmap &>/dev/null; then
        info "  nmap found"
        tools_installed=1
    else
        warn "  nmap not found (recommended for best subnet scanning)"
        if command -v yum &>/dev/null; then
            read -r -p "  Install nmap? [Y/n]: " yn
            yn="${yn:-Y}"
            if [[ "$yn" =~ ^[Yy] ]]; then
                yum install -y nmap && tools_installed=1
            fi
        elif command -v apt-get &>/dev/null; then
            read -r -p "  Install nmap? [Y/n]: " yn
            yn="${yn:-Y}"
            if [[ "$yn" =~ ^[Yy] ]]; then
                apt-get update && apt-get install -y nmap && tools_installed=1
            fi
        fi
    fi

    if ! command -v fping &>/dev/null; then
        warn "  fping not found (alternative to nmap for fast scans)"
    else
        info "  fping found"
        tools_installed=1
    fi

    if ! command -v arp-scan &>/dev/null; then
        warn "  arp-scan not found (for local L2 subnet scanning)"
    else
        info "  arp-scan found"
        tools_installed=1
    fi

    if [[ $tools_installed -eq 0 ]]; then
        warn "  No scan tools installed. Agent will fall back to basic ping (slow)."
    fi

    # Grant capabilities for non-root ping if needed
    if command -v setcap &>/dev/null && command -v nmap &>/dev/null; then
        setcap cap_net_raw,cap_net_admin,cap_net_bind_service+eip "$(which nmap)" 2>/dev/null || true
    fi
}

test_connection() {
    info "Testing connection to CMDB API..."
    python3 -c "
import json, sys
with open('${CONFIG_FILE}') as f:
    cfg = json.load(f)
import hashlib, requests
path = '/api/v0.1/ci/s'
params = {'q': '_type:ipam_subnet', 'count': 1}
values = ''.join(str(params[k]) for k in sorted(params.keys()) if k not in ('_key', '_secret') and not isinstance(params[k], (dict, list)))
raw = ''.join([path, cfg['api_secret'], values]).encode('utf-8')
params['_secret'] = hashlib.sha1(raw).hexdigest()
params['_key'] = cfg['api_key']
try:
    r = requests.get(cfg['cmdb_url'].rstrip('/') + path, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    print(f'Connection OK, found {data.get(\"numfound\", 0)} subnets')
except Exception as e:
    print(f'Connection failed: {e}')
    sys.exit(1)
" || warn "Connection test failed, check your config and API URL"
}

show_usage() {
    local agent_id
    agent_id=$(python3 -c "import json; print(json.load(open('${CONFIG_FILE}')).get('agent_id', 'unknown'))" 2>/dev/null || echo "unknown")

    echo ""
    echo "============================================"
    echo "  CMDB Services Management"
    echo "  Agent ID: ${agent_id}"
    echo "============================================"
    echo ""
    echo "--- Subnet Scan Agent (OneAgent) ---"
    echo "  sudo systemctl start|stop|restart|status cmdb-agent"
    echo "  sudo journalctl -u cmdb-agent -f"
    echo "  sudo ${INSTALL_DIR}/cmdb_agent.py --once"
    echo "  sudo ${INSTALL_DIR}/cmdb_agent.py --scan-subnet 10.X.X.0/24"
    echo ""
    echo "--- IPAM Asset Sync + HTTP Scan Server (port 8900) ---"
    echo "  sudo systemctl start|stop|restart|status cmdb-agent-ipam-sync"
    echo "  sudo journalctl -u cmdb-agent-ipam-sync -f"
    echo "  sudo ${INSTALL_DIR}/ipam_sync.py --once"
    echo "  HTTP server (daemon): POST /scan, GET /health"
    echo ""
    echo "--- Config Validation ---"
    echo "  sudo ${INSTALL_DIR}/cmdb_agent.py --validate"
    echo "  sudo ${INSTALL_DIR}/ipam_sync.py --validate"
    echo ""
    echo "Logs: ${LOG_DIR}/"
    echo "Config: ${CONFIG_FILE}"
    echo ""
    echo ">>> Next Steps <<<"
    echo "  1. In the CMDB UI, create an IPAM subnet and set"
    echo "     the Scan Agent ID to: ${agent_id}"
    echo "  2. In Config Center -> Agent Config, add this agent"
    echo "     (host:port:auth_token) and set the same auth_token in"
    echo "     ${CONFIG_FILE}"
    echo ""
}

# --- Main ---
echo "============================================"
echo "  CMDB IPAM OneAgent & Sync Installation"
echo "============================================"
echo ""

check_root
check_prerequisites
install_scripts
install_scan_tools
setup_config
install_services
enable_services
start_services
test_connection
show_usage

info "Installation complete!"
