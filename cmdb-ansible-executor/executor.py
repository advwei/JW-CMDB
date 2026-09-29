import json
import logging
import re
import subprocess
from logging.handlers import WatchedFileHandler
from pathlib import Path
from uuid import uuid4

from config import ANSIBLE_BASE_DIR, ANSIBLE_INVENTORY_DIR, ANSIBLE_PLAYBOOK_DIR, ANSIBLE_TIMEOUT

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

ANSIBLE_LOG_DIR = ANSIBLE_BASE_DIR / "logs"
ANSIBLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
executor_logger = logging.getLogger("ansible-executor.executor")
log_handler = WatchedFileHandler(ANSIBLE_LOG_DIR / "executor_run.log", encoding="utf-8")
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
executor_logger.addHandler(log_handler)
executor_logger.setLevel(logging.INFO)
executor_logger.propagate = False

WINDOWS_KEYWORDS = {"windows", "win", "windows server", "windows_server"}

_RECAP_LINE = re.compile(r"^(?P<name>\S+)\s*:\s+(?P<metrics>.+)$")
_RECAP_METRIC = re.compile(r"([A-Za-z_]+)=(\d+)")

STATUS_SUCCESS = "Success"
STATUS_FAILED = "Failed"
STATUS_PARTIAL = "Partial"


def validate_safe_name(value, field_name):
    if not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{field_name} contains unsafe characters: {value}")


def format_inventory_value(value):
    text = str(value)
    if any(char.isspace() for char in text):
        return json.dumps(text, ensure_ascii=False)
    return text


def is_windows_os(os_version):
    if not os_version:
        return False
    return any(kw in os_version.lower() for kw in WINDOWS_KEYWORDS)


def parse_play_recap(stdout):
    recap = {}
    in_recap = False
    for line in (stdout or "").splitlines():
        if line.startswith("PLAY RECAP"):
            in_recap = True
            continue
        if not in_recap:
            continue
        match = _RECAP_LINE.match(line)
        if not match:
            continue
        metrics = {key: int(value) for key, value in _RECAP_METRIC.findall(match.group("metrics"))}
        if metrics:
            recap[match.group("name")] = metrics
    return recap


def status_from_metrics(metrics):
    if metrics.get("failed", 0) or metrics.get("unreachable", 0):
        return STATUS_FAILED
    return STATUS_SUCCESS


def summarize_status(host_statuses, returncode):
    statuses = list(host_statuses)
    if not statuses:
        return STATUS_SUCCESS if returncode == 0 else STATUS_FAILED
    if all(status == STATUS_SUCCESS for status in statuses):
        return STATUS_SUCCESS
    if all(status == STATUS_FAILED for status in statuses):
        return STATUS_FAILED
    return STATUS_PARTIAL


def build_host_results(hosts, stdout, returncode):
    recap = parse_play_recap(stdout)
    fallback = STATUS_SUCCESS if returncode == 0 else STATUS_FAILED
    host_results = {}
    for host in hosts:
        ip = host.get("ip", "")
        metrics = recap.get(ip)
        host_results[ip] = status_from_metrics(metrics) if metrics is not None else fallback
    return host_results


def resolve_playbook(playbook):
    validate_safe_name(playbook, "playbook")
    playbook_path = (ANSIBLE_PLAYBOOK_DIR / playbook).resolve()
    if playbook_path.parent != ANSIBLE_PLAYBOOK_DIR.resolve():
        raise ValueError("playbook must be in /opt/ansible/playbooks")
    if not playbook_path.exists():
        raise FileNotFoundError(f"playbook not found: {playbook_path}")
    return playbook_path


def _build_host_line(ip, custom_hostname, ansible_password):
    password_part = ""
    if ansible_password:
        password_part = f" ansible_password={format_inventory_value(ansible_password)}"
    return f"{ip} custom_hostname={format_inventory_value(custom_hostname)}{password_part}"


def _group_name(prefix, os_version, used_names):
    suffix = re.sub(r"[^A-Za-z0-9_]+", "_", os_version or "").strip("_").lower()
    if not suffix or suffix == prefix:
        name = f"{prefix}_default"
    elif suffix.startswith(f"{prefix}_"):
        name = suffix
    else:
        name = f"{prefix}_{suffix}"
    if name not in used_names:
        used_names.add(name)
        return name
    index = 2
    while f"{name}_{index}" in used_names:
        index += 1
    name = f"{name}_{index}"
    used_names.add(name)
    return name


def _collect_groups(hosts):
    used_names = set()
    groups = []
    group_index = {}

    for h in hosts:
        windows = is_windows_os(h.get("os_version", ""))
        prefix = "windows" if windows else "linux"
        os_version = h.get("os_version") or ""
        port = h.get("ansible_port") or (5985 if windows else 22)
        user = h.get("ansible_user") or ("Administrator" if windows else "root")
        key = (prefix, os_version, str(port), str(user))
        group = group_index.get(key)
        if group is None:
            group = {
                "name": _group_name(prefix, os_version, used_names),
                "prefix": prefix,
                "hosts": [],
                "port": port,
                "user": user,
            }
            group_index[key] = group
            groups.append(group)
        group["hosts"].append(h)

    return groups


def build_inventory(hosts, extra_params=None):
    groups = _collect_groups(hosts)
    lines = []

    for group in groups:
        lines.append(f"[{group['name']}]")
        for h in group["hosts"]:
            lines.append(_build_host_line(h["ip"], h["custom_hostname"], h.get("ansible_password", "")))
        lines.append("")
        lines.append(f"[{group['name']}:vars]")
        lines.append(f"ansible_port={format_inventory_value(group['port'])}")
        lines.append(f"ansible_user={format_inventory_value(group['user'])}")
        if group["prefix"] == "windows":
            lines.append("ansible_winrm_transport=ntlm")
            lines.append("ansible_winrm_server_cert_validation=ignore")
            lines.append("ansible_connection=winrm")
        else:
            lines.append("ansible_connection=ssh")
        lines.append("")

    children = []
    for prefix in ("linux", "windows"):
        names = [group["name"] for group in groups if group["prefix"] == prefix]
        if not names:
            continue
        lines.append(f"[{prefix}:children]")
        lines.extend(names)
        lines.append("")
        children.append(prefix)

    if children:
        lines.append("[targethost:children]")
        lines.extend(children)
        lines.append("")

    lines.append("[targethost:vars]")
    lines.append("ansible_python_interpreter=/usr/bin/python3")

    if extra_params:
        for key, value in extra_params.items():
            lines.append(f"{key}={format_inventory_value(value)}")

    lines.append("")
    return "\n".join(lines)


def list_playbooks():
    if not ANSIBLE_PLAYBOOK_DIR.exists():
        return []
    playbooks = []
    for f in sorted(ANSIBLE_PLAYBOOK_DIR.iterdir()):
        if f.suffix in (".yml", ".yaml") and f.is_file():
            playbooks.append(f.name)
    return playbooks


def run_playbook(hosts, playbook, new_password=None, extra_params=None):
    playbook_path = resolve_playbook(playbook)
    ANSIBLE_INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    inventory_path = ANSIBLE_INVENTORY_DIR / f"setup-{uuid4().hex}.ini"

    inventory_extra = dict(extra_params or {})
    if new_password:
        inventory_extra['new_password'] = new_password

    inventory_content = build_inventory(hosts, inventory_extra)
    inventory_path.write_text(inventory_content, encoding="utf-8")

    cmd = [
        "ansible-playbook",
        "-i", str(inventory_path),
        str(playbook_path),
        "-e", "target_hosts=targethost",
    ]

    host_summary = ", ".join(f"{h['ip']}({h['custom_hostname']})" for h in hosts[:5])
    if len(hosts) > 5:
        host_summary += f" ... 共{len(hosts)}台"

    executor_logger.info("=" * 60)
    executor_logger.info("执行 Ansible 剧本: %s", playbook)
    executor_logger.info("目标主机: %s", host_summary)
    executor_logger.info("主机数量: %d", len(hosts))
    executor_logger.info("额外参数: %s", extra_params or {})
    executor_logger.info("命令: %s", " ".join(cmd))
    executor_logger.info("Inventory 内容:\n%s", inventory_content)

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(ANSIBLE_PLAYBOOK_DIR),
            timeout=ANSIBLE_TIMEOUT
        )
        host_results = build_host_results(hosts, completed.stdout, completed.returncode)
        status = summarize_status(host_results.values(), completed.returncode)
        executor_logger.info("执行结果: %s (returncode=%s)", status, completed.returncode)
        executor_logger.info("主机结果: %s", ", ".join(
            f"{ip}={host_status}" for ip, host_status in host_results.items()))
        executor_logger.info("stdout:\n%s", completed.stdout[:5000])
        if completed.stderr:
            executor_logger.warning("stderr:\n%s", completed.stderr[:2000])
        return {
            "status": status,
            "returncode": completed.returncode,
            "host_results": host_results,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "playbook": str(playbook_path),
            "inventory": str(inventory_path),
        }
    except subprocess.TimeoutExpired:
        executor_logger.error("Ansible 执行超时（%s秒）", ANSIBLE_TIMEOUT)
        return {
            "status": STATUS_FAILED,
            "returncode": -1,
            "host_results": {},
            "stdout": "",
            "stderr": f"Ansible execution timed out after {ANSIBLE_TIMEOUT}s",
            "playbook": str(playbook_path),
            "inventory": str(inventory_path),
        }
    finally:
        try:
            inventory_path.unlink(missing_ok=True)
            executor_logger.info("临时 inventory 已清理: %s", inventory_path.name)
        except Exception:
            pass
