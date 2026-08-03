#!/bin/bash
#
# CMDB IPAM Agent Uninstaller
# Stops and removes all CMDB agent services, files, and configurations
#

set -euo pipefail

INSTALL_DIR="/opt/cmdb-agent"
SERVICE_DIR="/etc/systemd/system"

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

stop_services() {
    info "Stopping services..."
    for svc in cmdb-agent cmdb-agent-ipam-sync; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            systemctl stop "$svc"
            info "  Stopped $svc"
        fi
    done
}

disable_services() {
    info "Disabling services..."
    for svc in cmdb-agent cmdb-agent-ipam-sync; do
        if systemctl is-enabled --quiet "$svc" 2>/dev/null; then
            systemctl disable "$svc"
            info "  Disabled $svc"
        fi
    done
}

remove_services() {
    info "Removing service files..."
    for svc in cmdb-agent cmdb-agent-ipam-sync; do
        local svc_file="${SERVICE_DIR}/${svc}.service"
        if [[ -f "$svc_file" ]]; then
            rm -f "$svc_file"
            info "  Removed $svc_file"
        fi
    done
    systemctl daemon-reload
    info "  Reloaded systemd"
}

remove_files() {
    info "Removing installation directory: ${INSTALL_DIR}"
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        info "  Removed ${INSTALL_DIR}"
    fi
}

remove_legacy_files() {
    info "Checking for legacy files..."
    local legacy_dirs=(
        "/etc/cmdb_agent"
        "/var/lib/cmdb_agent"
        "/var/log/cmdb_agent"
        "/usr/local/bin/cmdb_agent.py"
        "/usr/local/bin/ipam_sync.py"
    )
    for dir in "${legacy_dirs[@]}"; do
        if [[ -e "$dir" ]]; then
            warn "  Found legacy path: $dir"
            read -r -p "  Remove $dir? [y/N]: " yn
            yn="${yn:-N}"
            if [[ "$yn" =~ ^[Yy] ]]; then
                rm -rf "$dir"
                info "  Removed $dir"
            fi
        fi
    done
}

show_summary() {
    echo ""
    echo "============================================"
    echo "  Uninstallation Complete"
    echo "============================================"
    echo ""
    echo "  Removed:"
    echo "    - Services: cmdb-agent, cmdb-agent-ipam-sync"
    echo "    - Installation: ${INSTALL_DIR}"
    echo ""
    echo "  Note: Scan tools (nmap, fping, arp-scan) were NOT removed."
    echo "  To remove them:"
    echo "    yum remove nmap fping arp-scan"
    echo ""
}

# --- Main ---
echo "============================================"
echo "  CMDB IPAM Agent Uninstaller"
echo "============================================"
echo ""

check_root

read -r -p "This will remove all CMDB agent services and files. Continue? [y/N]: " confirm
confirm="${confirm:-N}"
if [[ ! "$confirm" =~ ^[Yy] ]]; then
    info "Aborted."
    exit 0
fi

echo ""
stop_services
disable_services
remove_services
remove_files
remove_legacy_files
show_summary
