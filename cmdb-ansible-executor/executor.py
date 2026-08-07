import json
import logging
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from config import ANSIBLE_BASE_DIR, ANSIBLE_INVENTORY_DIR, ANSIBLE_PLAYBOOK_DIR, ANSIBLE_TIMEOUT

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")

ANSIBLE_LOG_DIR = ANSIBLE_BASE_DIR / "logs"
ANSIBLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
executor_logger = logging.getLogger("ansible-executor.executor")
log_handler = logging.FileHandler(ANSIBLE_LOG_DIR / "executor_run.log", encoding="utf-8")
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
executor_logger.addHandler(log_handler)
executor_logger.setLevel(logging.INFO)
executor_logger.propagate = False

WINDOWS_KEYWORDS = {"windows", "win", "windows server", "windows_server"}


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


def build_inventory(hosts, extra_params=None):
    linux_hosts = []
    windows_hosts = []

    for h in hosts:
        if is_windows_os(h.get("os_version", "")):
            windows_hosts.append(h)
        else:
            linux_hosts.append(h)

    lines = []

    if linux_hosts:
        lines.append("[linux]")
        for h in linux_hosts:
            lines.append(_build_host_line(h["ip"], h["custom_hostname"], h.get("ansible_password", "")))
        lines.append("")
        lines.append("[linux:vars]")
        lines.append("ansible_port=22")
        lines.append("ansible_user=root")
        lines.append("ansible_connection=ssh")
        lines.append("")

    if windows_hosts:
        lines.append("[windows]")
        for h in windows_hosts:
            lines.append(_build_host_line(h["ip"], h["custom_hostname"], h.get("ansible_password", "")))
        lines.append("")
        lines.append("[windows:vars]")
        lines.append("ansible_port=5985")
        lines.append("ansible_winrm_transport=ntlm")
        lines.append("ansible_winrm_server_cert_validation=ignore")
        lines.append("ansible_connection=winrm")
        lines.append("ansible_user=Administrator")
        lines.append("")

    if linux_hosts and windows_hosts:
        lines.append("[targethost:children]")
        lines.append("linux")
        lines.append("windows")
        lines.append("")
    elif linux_hosts:
        lines.append("[targethost:children]")
        lines.append("linux")
        lines.append("")
    elif windows_hosts:
        lines.append("[targethost:children]")
        lines.append("windows")
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
        executor_logger.info("执行结果: %s (returncode=%s)", "成功" if completed.returncode == 0 else "失败", completed.returncode)
        executor_logger.info("stdout:\n%s", completed.stdout[:5000])
        if completed.stderr:
            executor_logger.warning("stderr:\n%s", completed.stderr[:2000])
        return {
            "status": "Success" if completed.returncode == 0 else "Failed",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "playbook": str(playbook_path),
            "inventory": str(inventory_path),
        }
    except subprocess.TimeoutExpired:
        executor_logger.error("Ansible 执行超时（%s秒）", ANSIBLE_TIMEOUT)
        return {
            "status": "Failed",
            "returncode": -1,
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
