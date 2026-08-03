#!/bin/bash
#
# CMDB Agent Update Script
# Updates agent files in /opt/cmdb-agent and restarts services
#

set -euo pipefail

AGENT_SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/cmdb-agent"
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
        error "Please run as root (use sudo)"
        exit 1
    fi
}

check_files() {
    local missing=0
    for f in cmdb_agent.py ipam_sync.py cmdb-agent.service cmdb-agent-ipam-sync.service; do
        if [[ ! -f "${AGENT_SRC_DIR}/${f}" ]]; then
            error "Missing file: ${AGENT_SRC_DIR}/${f}"
            missing=1
        fi
    done
    if [[ $missing -eq 1 ]]; then
        exit 1
    fi
}

update_scripts() {
    info "Updating agent scripts to ${INSTALL_DIR}/..."
    
    mkdir -p "${INSTALL_DIR}" "${DATA_DIR}" "${LOG_DIR}"
    
    cp -f "${AGENT_SRC_DIR}/cmdb_agent.py" "${INSTALL_DIR}/cmdb_agent.py"
    chmod 755 "${INSTALL_DIR}/cmdb_agent.py"
    info "  cmdb_agent.py -> ${INSTALL_DIR}/cmdb_agent.py"

    cp -f "${AGENT_SRC_DIR}/ipam_sync.py" "${INSTALL_DIR}/ipam_sync.py"
    chmod 755 "${INSTALL_DIR}/ipam_sync.py"
    info "  ipam_sync.py -> ${INSTALL_DIR}/ipam_sync.py"
}

update_services() {
    info "Updating systemd service files..."
    cp -f "${AGENT_SRC_DIR}/cmdb-agent.service" /etc/systemd/system/cmdb-agent.service
    chmod 644 /etc/systemd/system/cmdb-agent.service
    info "  cmdb-agent.service -> /etc/systemd/system/"

    cp -f "${AGENT_SRC_DIR}/cmdb-agent-ipam-sync.service" /etc/systemd/system/cmdb-agent-ipam-sync.service
    chmod 644 /etc/systemd/system/cmdb-agent-ipam-sync.service
    info "  cmdb-agent-ipam-sync.service -> /etc/systemd/system/"

    systemctl daemon-reload
}

restart_services() {
    info "Restarting services..."
    systemctl restart cmdb-agent 2>/dev/null && info "  cmdb-agent restarted" || warn "  cmdb-agent not running, skipped"
    systemctl restart cmdb-agent-ipam-sync 2>/dev/null && info "  cmdb-agent-ipam-sync restarted" || warn "  cmdb-agent-ipam-sync not running, skipped"
}

show_status() {
    echo ""
    echo "=============================="
    echo "  Service Status"
    echo "=============================="
    for svc in cmdb-agent cmdb-agent-ipam-sync; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            echo -e "  ${GREEN}●${NC} $svc   running"
        else
            echo -e "  ${RED}✗${NC} $svc   not running"
        fi
    done
    echo ""
    info "View logs:"
    echo "  sudo journalctl -u cmdb-agent -n 50 --no-pager"
    echo "  sudo journalctl -u cmdb-agent-ipam-sync -n 50 --no-pager"
    echo ""
    info "Verify config:"
    echo "  sudo ${INSTALL_DIR}/cmdb_agent.py --validate"
    echo "  sudo ${INSTALL_DIR}/ipam_sync.py --validate"
    echo ""
    info "Config file: ${INSTALL_DIR}/config.json"
    info "Data directory: ${DATA_DIR}/"
    info "Log directory: ${LOG_DIR}/"
    echo ""
}

# --- Main ---
echo "============================================"
echo "  CMDB Agent Update"
echo "============================================"
echo ""

check_root
check_files
echo ""
update_scripts
update_services
restart_services
echo ""
show_status

info "Update complete!"
