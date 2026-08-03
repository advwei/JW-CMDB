import json
import logging
from functools import wraps

from flask import Flask, request, jsonify

from config import EXECUTOR_HOST, EXECUTOR_PORT, API_KEY
from executor import run_playbook, list_playbooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ansible-executor")

app = Flask(__name__)


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if api_key != API_KEY:
            return jsonify({"error": "Invalid API Key"}), 403
        return f(*args, **kwargs)
    return decorated


@app.route("/api/exec/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/exec/playbooks", methods=["GET"])
@require_api_key
def playbooks():
    return jsonify({"playbooks": list_playbooks()})


@app.route("/api/exec/run-playbook", methods=["POST"])
@require_api_key
def run():
    payload = request.get_json(silent=True) or {}

    hosts = payload.get("hosts")
    if not hosts:
        ip = payload.get("ip", "").strip()
        if ip:
            hosts = [{
                "ip": ip,
                "custom_hostname": payload.get("custom_hostname", "").strip(),
                "os_version": payload.get("os_version", "").strip(),
                "ansible_port": payload.get("ansible_port", 22),
                "ansible_user": payload.get("ansible_user", "root"),
                "ansible_password": payload.get("ansible_password", ""),
            }]

    if not hosts:
        return jsonify({"error": "hosts is required (or legacy ip field)"}), 400

    for i, h in enumerate(hosts):
        if not h.get("ip", "").strip():
            return jsonify({"error": f"hosts[{i}].ip is required"}), 400
        if not h.get("custom_hostname", "").strip():
            return jsonify({"error": f"hosts[{i}].custom_hostname is required"}), 400
        h["ip"] = h["ip"].strip()
        h["custom_hostname"] = h["custom_hostname"].strip()
        h.setdefault("os_version", "")
        h.setdefault("ansible_port", 22)
        h.setdefault("ansible_user", "root")
        h.setdefault("ansible_password", "")

    playbook = payload.get("playbook", "setup_server.yml")
    new_password = payload.get("new_password", "")
    extra_params = payload.get("extra_params") or {}

    if isinstance(extra_params, str):
        extra_params = {}
        for part in extra_params.split():
            if "=" in part:
                k, v = part.split("=", 1)
                extra_params[k] = v

    try:
        result = run_playbook(
            hosts=hosts,
            playbook=playbook,
            new_password=new_password or None,
            extra_params=extra_params or None,
        )
        host_summary = f"{len(hosts)} hosts"
        logger.info("Ansible result for %s: %s", host_summary, result["status"])
        return jsonify(result)
    except (ValueError, FileNotFoundError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("Unexpected error running playbook")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    logger.info("Starting Ansible Executor on %s:%s", EXECUTOR_HOST, EXECUTOR_PORT)
    app.run(host=EXECUTOR_HOST, port=EXECUTOR_PORT, debug=False)
