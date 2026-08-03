#!/usr/bin/env python3
"""
CMDB IPAM Asset Sync Service
Syncs asset CI (vmserver) private_ip to IPAM ipam_address records.
Marks IPs as used with assetname as description.

Also provides an HTTP server for on-demand subnet ping scanning.
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
import threading
import concurrent.futures
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
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
    "interval": 7200,
    "log_level": "INFO",
    "asset_types": ["vmserver", "server", "container"],
    "ip_fields": ["private_ip", "public_ip", "ip"],
    "name_fields": ["assetname", "hostname", "name"],
    "subnet_field": "subnet",
    "sync_on_delete": True,
    "agent_id": None,
    "auth_token": "",
    "http_port": 8900,
    "http_host": "0.0.0.0"
}


def setup_logging(level_name):
    level = getattr(logging, level_name.upper(), logging.INFO)
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(LOG_DIR, "ipam_sync.log")),
            logging.StreamHandler(sys.stdout)
        ]
    )


def _get_local_ips():
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


def load_config():
    if not os.path.exists(CONFIG_PATH):
        logging.warning("Config not found at %s, using defaults", CONFIG_PATH)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        cfg["cmdb_url"] = _resolve_cmdb_url(cfg)
        return cfg
    except (json.JSONDecodeError, IOError) as e:
        logging.error("Failed to load config: %s", e)
        sys.exit(1)


def api_auth(path, params, api_key, api_secret):
    values = "".join(
        str(params[k]) for k in sorted(params.keys())
        if k not in ("_key", "_secret") and not isinstance(params[k], (dict, list))
    )
    raw = "".join([path, api_secret, values]).encode("utf-8")
    params["_secret"] = hashlib.sha1(raw).hexdigest()
    params["_key"] = api_key
    return params


def _safe_request(method, cfg, path, params=None, json_data=None):
    if params is None:
        params = {}
    if json_data and method == "PUT":
        params.update(json_data)
    url = cfg["cmdb_url"].rstrip("/") + path
    params = api_auth(path, params, cfg["api_key"], cfg["api_secret"])
    try:
        if method == "GET":
            resp = requests.get(url, params=params, timeout=30)
        elif method == "PUT":
            resp = requests.put(url, params=params, timeout=30)
        else:
            resp = requests.post(url, json=params, timeout=30)
        if resp.status_code == 400:
            logging.error("API 400 error: %s %s | params=%s | body=%s", method, url, params, resp.text)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logging.debug("API %s %s failed: %s", method, path, e)
        raise


def api_get(cfg, path, params=None):
    return _safe_request("GET", cfg, path, params)


def api_post(cfg, path, params=None):
    return _safe_request("POST", cfg, path, params)


def api_put(cfg, path, json_data=None):
    return _safe_request("PUT", cfg, path, json_data=json_data)



def get_ci_ids_by_type(cfg, ci_type):
    """Get CI IDs for a specific CI type. Returns empty list if type doesn't exist."""
    ids = []
    page = 1
    while True:
        try:
            result = api_get(cfg, "/api/v0.1/ci/s", {
                "q": f"_type:{ci_type}",
                "count": 500,
                "page": page
            })
            items = result.get("result", [])
            if not items:
                break
            for item in items:
                ci_id = item.get("_id")
                if ci_id:
                    ids.append({"_id": ci_id})
            if len(items) < 500:
                break
            page += 1
        except requests.exceptions.HTTPError as e:
            resp = e.response
            if resp is not None:
                resp_text = resp.text[:200] if resp.text else ""
                if "does not exist" in resp_text or resp.status_code == 400:
                    logging.info("CI type '%s' does not exist or query error, skipping", ci_type)
                else:
                    logging.warning("Failed to fetch %s CI list: %s %s - %s", ci_type, resp.status_code, resp.reason, resp_text)
            else:
                logging.warning("Failed to fetch %s CI list: %s", ci_type, e)
            break
        except requests.RequestException as e:
            logging.warning("Failed to fetch %s CI list: %s", ci_type, e)
            break
    return ids


def get_ci_detail(cfg, ci_id):
    q = f"_id:{ci_id}"
    try:
        result = api_get(cfg, "/api/v0.1/ci/s", {"q": q, "ret_key": "name"})
        items = result.get("result", [])
        return items[0] if items else None
    except Exception as e:
        logging.error("Failed to fetch CI detail %s: %s", ci_id, e)
        return None


def _first_value(ci_dict, candidates):
    if isinstance(candidates, str):
        candidates = [candidates]
    for key in candidates:
        value = ci_dict.get(key)
        if value is not None and value != "":
            if isinstance(value, list):
                return value[0] if value else None
            return value
    return None


def _ip_to_int(ip):
    parts = [int(x) for x in ip.split(".")]
    return (parts[0] << 24) | (parts[1] << 16) | (parts[2] << 8) | parts[3]


def _ip_in_cidr(ip, cidr):
    try:
        import ipaddress
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ImportError:
        try:
            network, bits = cidr.split("/")
            bits = int(bits)
            ip_int = _ip_to_int(ip)
            net_int = _ip_to_int(network)
            mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
            return (ip_int & mask) == (net_int & mask)
        except (ValueError, IndexError):
            return False
    except ValueError:
        return False


def find_subnet_by_id(cfg, subnet_id):
    if not subnet_id:
        return None
    try:
        result = api_get(cfg, "/api/v0.1/ci/s", {
            "q": f"_type:ipam_subnet,_id:{subnet_id}",
            "ret_key": "name"
        })
        items = result.get("result", [])
        return items[0] if items else None
    except Exception as e:
        logging.warning("Error finding subnet by id %s: %s", subnet_id, e)
        return None


def find_subnet_by_ip(cfg, ip):
    q = "_type:ipam_subnet"
    try:
        result = api_get(cfg, "/api/v0.1/ci/s", {"q": q, "count": 1000, "ret_key": "name"})
        for subnet in result.get("result", []):
            cidr = subnet.get("cidr", "")
            if _ip_in_cidr(ip, cidr):
                return subnet
    except requests.exceptions.HTTPError as e:
        resp = e.response
        if resp is not None:
            logging.warning("Error searching subnets for IP %s: %s %s - %s", ip, resp.status_code, resp.reason, resp.text[:200])
        else:
            logging.warning("Error searching subnets for IP %s: %s", ip, e)
    except Exception as e:
        logging.warning("Error searching subnets for IP %s: %s", ip, e)
    return None


def get_enabled_subnet_ids(cfg):
    """Fetch UI-configured scan rules and return set of enabled subnet IDs for this agent."""
    agent_id = cfg.get("agent_id")
    if not agent_id:
        return None
    hostname = socket.gethostname()
    try:
        result = api_get(cfg, "/api/v0.1/adt/sync",
                         {"oneagent_id": agent_id, "oneagent_name": hostname})
        rules = result.get("subnet_scan_rules", []) or []
        enabled = set()
        for rule in rules:
            if rule.get("scan_enabled"):
                enabled.add(rule["ci_id"])
        if enabled:
            logging.info("UI scan rules enabled for %d subnets", len(enabled))
            return enabled
        logging.info("No enabled scan rules found for agent %s", agent_id)
        return None
    except Exception as e:
        logging.warning("Failed to fetch scan rules, will sync all: %s", e)
        return None


def sync_subnet_ips_batch(cfg, subnet_id, cidr, ips):
    """Sync a batch of IPs for a subnet in a single scan history API call."""
    if not ips:
        return
    exec_id = str(uuid.uuid4())
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "exec_id": exec_id,
        "ci_id": subnet_id,
        "cidr": cidr,
        "ips": ips,
        "start_at": now_str,
        "end_at": now_str,
        "status": 0,
        "ip_num": len(ips),
        "is_used": "1",
        "skip_assign_status": True,
        "stdout": "batch sync {} IPs".format(len(ips))
    }
    try:
        api_post(cfg, "/api/v0.1/ipam/history/scan", payload)
        logging.info("Batch synced %d IPs to subnet %s", len(ips), cidr)
    except Exception as e:
        logging.warning("Failed to batch sync IPs to subnet %s: %s", cidr, e)


def _valid_ip(ip):
    if not ip or ":" in ip or ip.startswith("127."):
        return False
    if not re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
        return False
    return True


def _find_subnet_for_ip(cfg, ip, subnet_ref=None):
    subnet_ci = None
    if subnet_ref:
        if isinstance(subnet_ref, dict):
            subnet_ci = find_subnet_by_id(cfg, subnet_ref.get("_id"))
        elif isinstance(subnet_ref, (int, float)) or (isinstance(subnet_ref, str) and subnet_ref.isdigit()):
            subnet_ci = find_subnet_by_id(cfg, int(subnet_ref))
        else:
            logging.debug("subnet_ref is not a numeric ID (%s), skipping find_subnet_by_id", subnet_ref)
    if not subnet_ci:
        subnet_ci = find_subnet_by_ip(cfg, ip)
    return subnet_ci


def sync_assets(cfg, asset_type, enabled_subnet_ids=None):
    logging.info("Syncing assets of type: %s", asset_type)
    ci_ids = get_ci_ids_by_type(cfg, asset_type)
    logging.info("Found %d CIs of type %s", len(ci_ids), asset_type)

    ip_fields = cfg.get("ip_fields", DEFAULT_CONFIG["ip_fields"])
    name_fields = cfg.get("name_fields", DEFAULT_CONFIG["name_fields"])
    subnet_field = cfg.get("subnet_field", DEFAULT_CONFIG["subnet_field"])

    synced_ips = set()
    subnet_ip_map = {}

    for ci_entry in ci_ids:
        ci_id = ci_entry.get("_id") or ci_entry.get("id")
        if not ci_id:
            continue

        ci = get_ci_detail(cfg, ci_id)
        if not ci:
            continue

        ip = _first_value(ci, ip_fields)
        if not ip:
            continue

        assetname = _first_value(ci, name_fields) or (ip[0] if isinstance(ip, list) else ip)
        subnet_ref = ci.get(subnet_field)

        ips_list = ip if isinstance(ip, list) else [ip]
        for single_ip in ips_list:
            if not _valid_ip(single_ip):
                continue

            logging.info("Processing IP %s (assetname=%s, asset_id=%s)", single_ip, assetname, ci_id)

            subnet_ci = _find_subnet_for_ip(cfg, single_ip, subnet_ref)
            if subnet_ci:
                sub_id = subnet_ci.get("_id")
                cidr = subnet_ci.get("cidr", "")
                if sub_id and cidr:
                    if sub_id not in subnet_ip_map:
                        subnet_ip_map[sub_id] = {"ips": set(), "cidr": cidr}
                    subnet_ip_map[sub_id]["ips"].add(single_ip)
            else:
                payload = {
                    "ci_type": "ipam_address",
                    "ip": single_ip,
                    "name": assetname,
                    "assign_status": 0,
                    "is_used": 1
                }
                try:
                    api_post(cfg, "/api/v0.1/ci", payload)
                    logging.info("Created IP %s (asset=%s) directly (no subnet matched)", single_ip, assetname)
                except Exception as e:
                    logging.warning("Failed to create IP %s directly: %s", single_ip, e)

            synced_ips.add(single_ip)

    for sub_id, data in subnet_ip_map.items():
        if enabled_subnet_ids is not None and sub_id not in enabled_subnet_ids:
            logging.debug("Skipping subnet %s - not in enabled scan rules", sub_id)
            continue
        sync_subnet_ips_batch(cfg, sub_id, data["cidr"], list(data["ips"]))

    return synced_ips


def mark_unused_ips(cfg, active_ips):
    if not active_ips:
        return
    try:
        result = api_get(cfg, "/api/v0.1/ci/s", {"q": "_type:ipam_address", "count": 5000})
        for ci in result.get("result", []):
            ip = ci.get("ip", "")
            ci_id = ci.get("_id")
            ip_used = ci.get("is_used", False)
            if ip and ci_id and ip not in active_ips and ip_used:
                logging.info("Releasing IP %s (ci_id=%s) - no longer in any asset", ip, ci_id)
                try:
                    api_put(cfg, "/api/v0.1/ci/{}".format(ci_id), {"is_used": False})
                except Exception as e:
                    logging.warning("Failed to release IP %s: %s", ip, e)
    except requests.exceptions.HTTPError as e:
        resp = e.response
        if resp is not None:
            logging.warning("Failed to query IPAM addresses: %s %s - %s", resp.status_code, resp.reason, resp.text[:200])
        else:
            logging.warning("Failed to query IPAM addresses: %s", e)
    except Exception as e:
        logging.warning("Failed to query IPAM addresses: %s", e)


def write_state(synced_ips, asset_types):
    os.makedirs(STATE_DIR, exist_ok=True)
    state_path = os.path.join(STATE_DIR, "ipam_sync_state.json")
    try:
        prev = set()
        if os.path.exists(state_path):
            with open(state_path) as f:
                data = json.load(f)
                prev = set(data.get("synced_ips", []))

        new_ips = synced_ips - prev
        removed_ips = prev - synced_ips

        with open(state_path, "w") as f:
            json.dump({
                "last_sync": datetime.now().isoformat(),
                "synced_ips": sorted(synced_ips),
                "asset_types": asset_types
            }, f, indent=2)

        return new_ips, removed_ips
    except IOError as e:
        logging.error("Failed to write state: %s", e)
        return set(), set()


def sync_loop(cfg):
    asset_types = cfg.get("asset_types", DEFAULT_CONFIG["asset_types"])

    while True:
        logging.info("Starting IPAM asset sync cycle")
        enabled_subnet_ids = get_enabled_subnet_ids(cfg)
        all_active_ips = set()
        for atype in asset_types:
            try:
                ips = sync_assets(cfg, atype, enabled_subnet_ids)
                all_active_ips.update(ips)
            except Exception as e:
                logging.error("Error syncing %s: %s", atype, e)

        new_ips, removed_ips = write_state(all_active_ips, asset_types)

        logging.info("Sync cycle complete: %d active IPs, %d new, %d removed",
                     len(all_active_ips), len(new_ips), len(removed_ips))

        interval = cfg.get("interval", DEFAULT_CONFIG["interval"])
        if interval <= 0:
            break
        time.sleep(interval)


def run_once(cfg):
    asset_types = cfg.get("asset_types", DEFAULT_CONFIG["asset_types"])
    enabled_subnet_ids = get_enabled_subnet_ids(cfg)
    all_active_ips = set()
    for atype in asset_types:
        try:
            ips = sync_assets(cfg, atype, enabled_subnet_ids)
            all_active_ips.update(ips)
        except Exception as e:
            logging.error("Error syncing %s: %s", atype, e)

    write_state(all_active_ips, asset_types)
    logging.info("Single sync complete: %d active IPs", len(all_active_ips))


# ── HTTP Scan Server ──

_agent_config = {}


class ScanRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/scan":
            return self._send_json(404, {"error": "not found"})

        token = self.headers.get("X-Auth-Token", "")
        if token != _agent_config.get("auth_token", ""):
            return self._send_json(401, {"error": "unauthorized"})

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        subnet_id = body.get("subnet_id")
        cidr = body.get("cidr")
        exec_id = body.get("exec_id")

        if not all([subnet_id, cidr, exec_id]):
            return self._send_json(400, {"error": "missing required fields: subnet_id, cidr, exec_id"})

        threading.Thread(
            target=run_ping_scan, args=(_agent_config, subnet_id, cidr, exec_id), daemon=True
        ).start()
        self._send_json(200, {"code": 200, "message": "scan started"})

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, fmt, *args):
        logging.info("HTTP %s - %s", self.client_address[0], fmt % args)


def run_ping_scan(cfg, subnet_id, cidr, exec_id):
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        logging.error("Invalid CIDR for scan: %s", cidr)
        return

    hosts = list(network.hosts())
    logging.info("Ping scan starting for %s (%d hosts, exec_id=%s)", cidr, len(hosts), exec_id)

    online = []

    def _ping(ip):
        try:
            if sys.platform.startswith("win"):
                cmd = ["ping", "-n", "1", "-w", "1000", str(ip)]
            else:
                cmd = ["ping", "-c", "1", "-W", "1", str(ip)]
            return subprocess.run(cmd, capture_output=True, timeout=3).returncode == 0
        except Exception:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        fut_map = {ex.submit(_ping, ip): ip for ip in hosts}
        for f in concurrent.futures.as_completed(fut_map):
            try:
                if f.result():
                    online.append(str(fut_map[f]))
            except Exception:
                pass

    online_set = set(online)
    offline = [str(h) for h in hosts if str(h) not in online_set]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "exec_id": exec_id,
        "ci_id": subnet_id,
        "cidr": cidr,
        "ips": online,
        "offline_ips": offline,
        "start_at": now_str,
        "end_at": now_str,
        "status": 0,
        "ip_num": len(online),
        "stdout": "ping scan {}/{} online".format(len(online), len(hosts)),
        "is_used": "1"
    }

    try:
        api_post(cfg, "/api/v0.1/ipam/history/scan", payload)
        logging.info("Ping scan done for %s: %d/%d online", cidr, len(online), len(hosts))
    except Exception as e:
        logging.error("Failed to report ping scan results for %s: %s", cidr, e)


def start_http_server(cfg):
    global _agent_config
    _agent_config.update(cfg)
    port = int(cfg.get("http_port", 8900))
    host = cfg.get("http_host", "0.0.0.0")
    server = HTTPServer((host, port), ScanRequestHandler)
    logging.info("HTTP scan server listening on %s:%s", host, port)
    server.serve_forever()


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
    parser = argparse.ArgumentParser(description="CMDB IPAM Asset Sync Service")
    parser.add_argument("-c", "--config", default=CONFIG_PATH, help="Config file path")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--validate", action="store_true", help="Validate config and exit")
    parser.add_argument("--sync-type", help="Sync only this CI type (e.g. vmserver)")
    args = parser.parse_args()

    if args.config:
        CONFIG_PATH = args.config

    cfg = load_config()

    if args.sync_type:
        cfg["asset_types"] = [args.sync_type]

    setup_logging(cfg.get("log_level", "INFO"))

    if args.validate:
        errors = validate_config(cfg)
        if errors:
            for e in errors:
                print(f"ERROR: {e}")
            sys.exit(1)
        print("Config is valid")
        return

    errors = validate_config(cfg)
    if errors:
        for e in errors:
            logging.error("Config error: %s", e)
        sys.exit(1)

    threading.Thread(target=start_http_server, args=(cfg,), daemon=True).start()

    if args.once:
        run_once(cfg)
    else:
        sync_loop(cfg)


if __name__ == "__main__":
    main()
