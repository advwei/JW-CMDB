#!/usr/bin/env python3
"""
CMDB IPAM OneAgent
- Registers with CMDB and polls for scan tasks via GET /api/v0.1/adt/sync
- Scans local host network interfaces (IPs, MACs) and reports to IPAM
- Performs subnet ping-sweep scans when assigned subnet scan rules
- Reports results via POST /api/v0.1/ipam/history/scan
"""

import hashlib
import ipaddress
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import uuid
import argparse
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Install with: pip install requests")
    sys.exit(1)

CONFIG_PATH = "/opt/cmdb-agent/config.json"
STATE_DIR = "/opt/cmdb-agent/data"
LOG_DIR = "/opt/cmdb-agent/logs"

DEFAULT_CONFIG = {
    "cmdb_url": "http://localhost:8000",
    "api_key": "",
    "api_secret": "",
    "agent_id": "",
    "interval": 7200,
    "log_level": "INFO",
    "skip_interfaces": ["lo", "docker*", "veth*", "br-*", "tun*", "virbr*"],
    "scan_method": "auto",
    "scan_concurrency": 50,
    "ping_timeout": 2,
    "subnet_scan_interval": 7200
}

IFACE_PATTERN_CACHE = {}


def _pattern_to_regex(pattern):
    if pattern not in IFACE_PATTERN_CACHE:
        r = "^" + re.escape(pattern).replace("\\*", ".*").replace("\\?", ".") + "$"
        IFACE_PATTERN_CACHE[pattern] = re.compile(r)
    return IFACE_PATTERN_CACHE[pattern]


def _match_interface(iface, patterns):
    return any(_pattern_to_regex(p).match(iface) for p in patterns)


def setup_logging(level_name):
    level = getattr(logging, level_name.upper(), logging.INFO)
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(os.path.join(LOG_DIR, "cmdb_agent.log")),
                  logging.StreamHandler(sys.stdout)])


def load_config():
    if not os.path.exists(CONFIG_PATH):
        logging.warning("Config not found at %s, using defaults", CONFIG_PATH)
        cfg = dict(DEFAULT_CONFIG)
    else:
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
        except (json.JSONDecodeError, IOError) as e:
            logging.error("Failed to load config: %s", e)
            sys.exit(1)

    if not cfg.get("agent_id"):
        h = hashlib.sha1(socket.gethostname().encode()).hexdigest()[:6]
        cfg["agent_id"] = "0x" + h
    cfg["cmdb_url"] = _resolve_cmdb_url(cfg)
    return cfg


def _get_local_ips():
    """Return set of all IPs assigned to local interfaces."""
    ips = {"127.0.0.1", "localhost"}
    try:
        hostname = socket.gethostname()
        ips.add(hostname)
        ips.add(socket.gethostbyname(hostname))
    except Exception:
        pass
    sys_net = Path("/sys/class/net")
    if sys_net.exists():
        for iface_path in sys_net.iterdir():
            if not iface_path.is_dir():
                continue
            try:
                oper = (iface_path / "operstate").read_text().strip()
                if oper not in ("up", "unknown"):
                    continue
            except (IOError, OSError):
                continue
            try:
                ip_out = subprocess.check_output(
                    ["ip", "-o", "addr", "show", "dev", iface_path.name],
                    stderr=subprocess.DEVNULL, text=True)
                for line in ip_out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        ips.add(parts[3].split("/")[0])
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
    return ips


def _resolve_cmdb_url(cfg):
    url = cfg.get("cmdb_url", "")
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return url
    local_ips = _get_local_ips()
    if host not in local_ips:
        return url
    replacement = f"{parsed.scheme}://127.0.0.1"
    if parsed.port:
        replacement += f":{parsed.port}"
    logging.info("cmdb_url host %s is local, using 127.0.0.1 to avoid Docker routing issues", host)
    return replacement


def api_auth(path, params, api_key, api_secret):
    values = "".join(str(params[k]) for k in sorted(params.keys())
                     if k not in ("_key", "_secret") and not isinstance(params[k], (dict, list)))
    raw = "".join([path, api_secret, values]).encode("utf-8")
    params["_secret"] = hashlib.sha1(raw).hexdigest()
    params["_key"] = api_key
    return params


def api_get(cfg, path, params=None):
    if params is None:
        params = {}
    url = cfg["cmdb_url"].rstrip("/") + path
    p = api_auth(path, dict(params), cfg["api_key"], cfg["api_secret"])
    resp = requests.get(url, params=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


def api_post(cfg, path, params=None):
    if params is None:
        params = {}
    url = cfg["cmdb_url"].rstrip("/") + path
    p = api_auth(path, dict(params), cfg["api_key"], cfg["api_secret"])
    resp = requests.post(url, json=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Local Host Interface Scan ──────────────────────────────

def get_host_interfaces(cfg):
    interfaces = {}
    sys_net = Path("/sys/class/net")
    if not sys_net.exists():
        return interfaces

    skip = cfg.get("skip_interfaces", [])
    for iface_path in sys_net.iterdir():
        if not iface_path.is_dir():
            continue
        iface = iface_path.name
        if _match_interface(iface, skip):
            continue
        oper = (iface_path / "operstate").read_text().strip()
        if oper not in ("up", "unknown"):
            continue
        mac = (iface_path / "address").read_text().strip().upper()
        if mac in ("", "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            mac = ""
        interfaces[iface] = {"mac": mac, "ips": []}

    try:
        out = subprocess.check_output(["ip", "-o", "addr", "show"], stderr=subprocess.DEVNULL, text=True)
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) < 4:
                continue
            iface = parts[1].rstrip(":")
            if iface not in interfaces:
                continue
            ip = parts[3].split("/")[0]
            interfaces[iface]["ips"].append(ip)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.warning("'ip addr' not available")
    return interfaces


def get_default_gateway():
    try:
        out = subprocess.check_output(["ip", "route", "show", "default"], stderr=subprocess.DEVNULL, text=True)
        for line in out.splitlines():
            parts = line.strip().split()
            if "via" in parts:
                return parts[parts.index("via") + 1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def find_subnet_by_ip(cfg, ip):
    q = "_type:ipam_subnet"
    try:
        result = api_get(cfg, "/api/v0.1/ci/s", {"q": q, "count": 1000})
        for subnet in result.get("result", []):
            cidr = subnet.get("cidr", "")
            if _ip_in_cidr(ip, cidr):
                return subnet
    except Exception as e:
        logging.warning("Error searching subnets for IP %s (cmdb_url=%s): %s", ip, cfg.get("cmdb_url"), e)
    return None


def _ip_in_cidr(ip, cidr):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def sync_host_ips(cfg):
    interfaces = get_host_interfaces(cfg)
    hostname = socket.gethostname()
    found = []

    for iface, info in interfaces.items():
        for ip in info["ips"]:
            if ":" in ip or ip.startswith("127."):
                continue
            # Find the subnet that contains this IP
            subnet = find_subnet_by_ip(cfg, ip)
            if subnet:
                subnet_id = subnet.get("_id")
                cidr = subnet.get("cidr", "")
                exec_id = str(uuid.uuid4())
                start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                payload = {
                    "exec_id": exec_id,
                    "ci_id": subnet_id,
                    "cidr": cidr,
                    "ips": [ip],
                    "start_at": start_at,
                    "end_at": start_at,
                    "status": 0,
                    "ip_num": 1,
                    "stdout": f"Host: {hostname}, Interface: {iface}, MAC: {info.get('mac', '')}"
                }
                try:
                    api_post(cfg, "/api/v0.1/ipam/history/scan", payload)
                    logging.info("Synced host IP %s (subnet=%s, iface=%s)", ip, cidr, iface)
                except Exception as e:
                    logging.warning("Failed to sync host IP %s: %s", ip, e)
            else:
                logging.info("No matching subnet found for host IP %s, skipping", ip)
            found.append(ip)
    return found


# ── Subnet Scanning (Ping Sweep) ────────────────────────────

def _detect_scan_tool():
    for tool, args in [("nmap", ["nmap", "--version"]),
                       ("fping", ["fping", "-v"]),
                       ("arp-scan", ["arp-scan", "--version"])]:
        if shutil.which(tool):
            try:
                subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                logging.info("Using scan tool: %s", tool)
                return tool
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
                continue
    logging.warning("No advanced scan tool found, falling back to ping")
    return "ping"


def _scan_with_nmap(cidr, timeout, concurrency):
    try:
        out = subprocess.check_output(
            ["nmap", "-sn", "-n", "--max-parallelism", str(concurrency),
             "--max-rtt-timeout", f"{timeout*1000}ms",
             "--min-hostgroup", "256", cidr],
            stderr=subprocess.DEVNULL, text=True, timeout=300)
        ips = re.findall(r"Nmap scan report for (\d+\.\d+\.\d+\.\d+)", out)
        return ips
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _scan_with_fping(cidr, timeout, concurrency):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        if network.num_addresses > 65536:
            logging.warning("Subnet too large for fping: %s", cidr)
            return None
        out = subprocess.check_output(
            ["fping", "-a", "-g", cidr, "-r", "0", "-t", str(int(timeout * 1000))],
            stderr=subprocess.DEVNULL, text=True, timeout=300)
        return [ip for ip in out.strip().split("\n") if ip]
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, TypeError):
        return None


def _scan_with_arpscan(cidr, timeout, concurrency):
    try:
        out = subprocess.check_output(
            ["arp-scan", "--retry=1", "--timeout=" + str(int(timeout * 250)),
             cidr],
            stderr=subprocess.DEVNULL, text=True, timeout=120)
        ips = re.findall(r"^(\d+\.\d+\.\d+\.\d+)\s", out, re.MULTILINE)
        return ips
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _scan_with_ping(cidr, timeout, concurrency):
    network = ipaddress.ip_network(cidr, strict=False)
    if network.num_addresses > 1024:
        logging.warning("Subnet too large for ping scan: %s (%d hosts)", cidr, network.num_addresses)
        return []
    live = []
    for host in network.hosts():
        ip = str(host)
        try:
            subprocess.run(["ping", "-c", "1", "-W", str(timeout), ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout + 2)
            live.append(ip)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return live


def scan_subnet(cfg, cidr):
    method = cfg.get("scan_method", "auto")
    timeout = cfg.get("ping_timeout", 2)
    concurrency = cfg.get("scan_concurrency", 50)

    if not _is_valid_cidr(cidr):
        logging.error("Invalid CIDR: %s", cidr)
        return {"online": [], "offline": []}

    logging.info("Scanning subnet %s (method=%s, timeout=%ds)", cidr, method, timeout)

    if method == "nmap":
        online = _scan_with_nmap(cidr, timeout, concurrency)
    elif method == "fping":
        online = _scan_with_fping(cidr, timeout, concurrency)
    elif method == "arp-scan":
        online = _scan_with_arpscan(cidr, timeout, concurrency)
    elif method == "ping":
        online = _scan_with_ping(cidr, timeout, concurrency)
    else:  # auto
        online = _scan_with_nmap(cidr, timeout, concurrency)
        if online is None:
            online = _scan_with_arpscan(cidr, timeout, concurrency)
        if online is None:
            online = _scan_with_fping(cidr, timeout, concurrency)
        if online is None:
            online = _scan_with_ping(cidr, timeout, concurrency)

    if online is None:
        online = []

    online = [ip for ip in online if _is_valid_ip(ip)]
    online = sorted(set(online))

    all_hosts = [str(h) for h in ipaddress.ip_network(cidr, strict=False).hosts()
                 if _is_valid_ip(str(h))]
    offline = sorted(set(all_hosts) - set(online))

    logging.info("Subnet %s scan complete: %d online, %d offline", cidr, len(online), len(offline))
    return {"online": online, "offline": offline}


def _is_valid_cidr(cidr):
    try:
        ipaddress.ip_network(cidr, strict=False)
        return True
    except ValueError:
        return False


def _is_valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


# ── Cron Scheduling ────────────────────────────────────────

def _cron_to_interval(cron_expr):
    """Convert common cron expressions to interval in seconds."""
    if not cron_expr or cron_expr.strip() == "":
        return None
    parts = cron_expr.strip().split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts[:5]
    # */n * * * * → every n minutes
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        n = int(minute[2:])
        return n * 60
    # n * * * * → every hour at minute n
    if minute != "*" and "/" not in minute and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return 3600
    # * */n * * * → every n hours
    if minute == "0" and hour.startswith("*/") and dom == "*" and month == "*" and dow == "*":
        n = int(hour[2:])
        return n * 3600
    # 0 0 * * * → daily at midnight
    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow == "*":
        return 86400
    # 0 0 * * 0 → weekly
    if minute == "0" and hour == "0" and dom == "*" and month == "*" and dow != "*":
        return 604800
    return None


def _is_scan_due(rule, last_subnet_scans, subnet_min_interval):
    """Check if a subnet scan is due based on cron or interval."""
    cron = rule.get("cron", "")
    ci_id = rule.get("ci_id")
    last_scan = last_subnet_scans.get(str(ci_id), rule.get("last_scan_time"))

    interval = _cron_to_interval(cron)
    if interval is None:
        interval = subnet_min_interval

    if not last_scan:
        created_at = rule.get("created_at")
        if created_at:
            try:
                created_dt = datetime.strptime(str(created_at)[:19], "%Y-%m-%d %H:%M:%S")
                elapsed = (datetime.now() - created_dt).total_seconds()
                return elapsed >= interval
            except ValueError:
                pass
        return False
    try:
        last_dt = datetime.strptime(str(last_scan)[:19], "%Y-%m-%d %H:%M:%S")
        elapsed = (datetime.now() - last_dt).total_seconds()
        return elapsed >= interval
    except ValueError:
        return True


# ── CMDB Task Protocol ─────────────────────────────────────

def poll_scan_tasks(cfg, last_update_at=None):
    agent_id = cfg["agent_id"]
    hostname = socket.gethostname()
    params = {"oneagent_id": agent_id, "oneagent_name": hostname}
    if last_update_at:
        params["last_update_at"] = last_update_at

    try:
        result = api_get(cfg, "/api/v0.1/adt/sync", params)
        rules = result.get("subnet_scan_rules", []) or []
        new_last = result.get("last_update_at", last_update_at)
        return rules, new_last
    except requests.RequestException as e:
        if "401" in str(e) or "403" in str(e):
            logging.warning("Auth error polling tasks: %s", e)
        else:
            logging.warning("Failed to poll tasks: %s", e)
        return [], last_update_at


def report_scan_result(cfg, ci_id, cidr, online_ips, exec_id, start_at, end_at,
                       status=0, stdout="", offline_ips=None):
    payload = {
        "exec_id": exec_id,
        "ci_id": ci_id,
        "cidr": cidr,
        "ips": online_ips,
        "start_at": start_at,
        "end_at": end_at,
        "status": status,
        "stdout": stdout,
        "ip_num": len(online_ips),
        "is_used": "1"
    }
    if offline_ips:
        payload["offline_ips"] = offline_ips
    try:
        url = cfg["cmdb_url"].rstrip("/") + "/api/v0.1/ipam/history/scan"
        p = api_auth("/api/v0.1/ipam/history/scan", dict(payload), cfg["api_key"], cfg["api_secret"])
        resp = requests.post(url, json=p, timeout=30)
        if resp.status_code >= 400:
            logging.error("Report scan result failed for %s: %s %s - %s", cidr, resp.status_code, resp.reason, resp.text[:200])
            return False
        logging.info("Reported scan result for %s: %d online, %d offline",
                     cidr, len(online_ips), len(offline_ips) if offline_ips else 0)
        return True
    except requests.RequestException as e:
        logging.error("Failed to report scan result for %s: %s", cidr, e)
        return False


# ── State Management ───────────────────────────────────────

def load_state():
    p = os.path.join(STATE_DIR, "cmdb_agent_state.json")
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    p = os.path.join(STATE_DIR, "cmdb_agent_state.json")
    try:
        with open(p, "w") as f:
            json.dump(state, f, indent=2)
    except IOError as e:
        logging.error("Failed to save state: %s", e)


# ── Main Loop ──────────────────────────────────────────────

def main_loop(cfg):
    state = load_state()
    last_update_at = state.get("last_update_at")
    last_subnet_scans = state.get("last_subnet_scans", {})
    last_host_scan = state.get("last_host_scan")
    cached_rules = state.get("cached_rules", [])

    host_scan_interval = cfg.get("interval", 7200)
    subnet_min_interval = cfg.get("subnet_scan_interval", 7200)

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info("=== Scan cycle start ===")

        # 1. Poll for scan tasks from CMDB
        rules, new_last = poll_scan_tasks(cfg, last_update_at)
        if new_last:
            last_update_at = new_last

        # Cache rules when poll returns data; fall back to cache when empty
        if rules:
            cached_rules = rules
        else:
            rules = cached_rules

        # 2. Host interface scan (every interval)
        host_ips = []
        if host_scan_interval > 0:
            host_ips = sync_host_ips(cfg)
            last_host_scan = now

        # 3. Execute subnet scan tasks that are due (respecting each rule's cron)
        for rule in rules:
            ci_id = rule.get("ci_id")
            cidr = rule.get("cidr")
            scan_enabled = rule.get("scan_enabled", True)
            if not ci_id or not cidr or not scan_enabled:
                continue

            if not _is_scan_due(rule, last_subnet_scans, subnet_min_interval):
                logging.debug("Skipping subnet %s (not due yet)", cidr)
                continue

            exec_id = str(uuid.uuid4())
            start_at = now
            logging.info("Scanning subnet %s (ci_id=%s)", cidr, ci_id)

            try:
                result = scan_subnet(cfg, cidr)
                live_ips = result["online"]
                dead_ips = result["offline"]
                report_scan_result(cfg, ci_id, cidr, live_ips, exec_id, start_at, now,
                                   offline_ips=dead_ips)
                last_subnet_scans[str(ci_id)] = now
            except Exception as e:
                logging.error("Error scanning subnet %s: %s", cidr, e)
                report_scan_result(cfg, ci_id, cidr, [], exec_id, start_at, now,
                                   status=1, stdout=str(e))

        # Save state
        save_state({
            "last_update_at": last_update_at,
            "last_subnet_scans": last_subnet_scans,
            "last_host_scan": last_host_scan,
            "host_ips_found": len(host_ips),
            "cached_rules": cached_rules,
        })

        interval = cfg.get("interval", DEFAULT_CONFIG["interval"])
        if interval <= 0:
            break
        logging.info("Sleeping %d seconds until next cycle", interval)
        time.sleep(interval)


def run_once(cfg):
    logging.info("Running single cycle")

    # Quick host scan
    sync_host_ips(cfg)

    # Poll for tasks and scan all assigned subnets
    rules, _ = poll_scan_tasks(cfg)
    for rule in rules:
        ci_id = rule.get("ci_id")
        cidr = rule.get("cidr")
        scan_enabled = rule.get("scan_enabled", True)
        if not ci_id or not cidr or not scan_enabled:
            continue

        exec_id = str(uuid.uuid4())
        start_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info("Scanning subnet %s", cidr)
        try:
            result = scan_subnet(cfg, cidr)
            report_scan_result(cfg, ci_id, cidr, result["online"], exec_id, start_at, start_at,
                               offline_ips=result["offline"])
        except Exception as e:
            logging.error("Error scanning subnet %s: %s", cidr, e)


def validate_config(cfg):
    errors = []
    if not cfg.get("cmdb_url"):
        errors.append("cmdb_url is required")
    if not cfg.get("api_key"):
        errors.append("api_key is required")
    if not cfg.get("api_secret"):
        errors.append("api_secret is required")
    return errors


def main():
    global CONFIG_PATH
    import socket

    parser = argparse.ArgumentParser(description="CMDB IPAM OneAgent")
    parser.add_argument("-c", "--config", default=CONFIG_PATH, help="Config file path")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--validate", action="store_true", help="Validate config and exit")
    parser.add_argument("--scan-subnet", help="Scan a specific CIDR (e.g. 10.X.X.0/24)")
    args = parser.parse_args()

    if args.config:
        CONFIG_PATH = args.config

    cfg = load_config()
    setup_logging(cfg.get("log_level", "INFO"))
    logging.info("Agent ID: %s, Hostname: %s", cfg.get("agent_id"), socket.gethostname())

    if args.validate:
        errors = validate_config(cfg)
        if errors:
            for e in errors:
                print(f"ERROR: {e}")
            sys.exit(1)
        print(f"Config is valid. Agent ID: {cfg.get('agent_id')}")
        return

    if args.scan_subnet:
        result = scan_subnet(cfg, args.scan_subnet)
        online = result["online"]
        offline = result["offline"]
        print(f"Found {len(online)} live hosts, {len(offline)} offline:")
        for ip in online:
            print(f"  [online]  {ip}")
        for ip in offline:
            print(f"  [offline] {ip}")
        return

    errors = validate_config(cfg)
    if errors:
        for e in errors:
            logging.error("Config error: %s", e)
        sys.exit(1)

    if args.once:
        run_once(cfg)
    else:
        main_loop(cfg)


if __name__ == "__main__":
    main()
