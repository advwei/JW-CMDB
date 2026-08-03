import os
from pathlib import Path

EXECUTOR_HOST = os.getenv("EXECUTOR_HOST", "0.0.0.0")
EXECUTOR_PORT = int(os.getenv("EXECUTOR_PORT", "18081"))
API_KEY = os.getenv("EXECUTOR_API_KEY", "change-me-to-a-secure-key")

ANSIBLE_BASE_DIR = Path(os.getenv("ANSIBLE_BASE_DIR", "/opt/ansible"))
ANSIBLE_INVENTORY_DIR = ANSIBLE_BASE_DIR / "inventory"
ANSIBLE_PLAYBOOK_DIR = ANSIBLE_BASE_DIR / "playbooks"
ANSIBLE_TIMEOUT = int(os.getenv("ANSIBLE_TIMEOUT", "600"))
