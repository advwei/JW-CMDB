import importlib
import os
import sys
import types

import pytest
from flask import Flask

CMDB_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CMDB_API_DIR not in sys.path:
    sys.path.insert(0, CMDB_API_DIR)


@pytest.fixture
def ansible_mod(monkeypatch):
    ci_stub = types.ModuleType("api.lib.cmdb.ci")
    ci_stub.CIManager = object

    const_stub = types.ModuleType("api.lib.cmdb.const")

    class RetKey(object):
        NAME = "name"

    const_stub.RetKey = RetKey

    cache_stub = types.ModuleType("api.lib.cmdb.cache")
    cache_stub.AttributeCache = object

    monkeypatch.setitem(sys.modules, "api.lib.cmdb.ci", ci_stub)
    monkeypatch.setitem(sys.modules, "api.lib.cmdb.const", const_stub)
    monkeypatch.setitem(sys.modules, "api.lib.cmdb.cache", cache_stub)

    sys.modules.pop("api.lib.cmdb.ansible", None)
    module = importlib.import_module("api.lib.cmdb.ansible")
    monkeypatch.setitem(sys.modules, "api.lib.cmdb.ansible", module)
    return module


def _app():
    app = Flask(__name__)
    app.config["ANSIBLE_EXECUTOR_URL"] = "http://executor:18081"
    app.config["ANSIBLE_EXECUTOR_API_KEY"] = "test-key"
    return app


def _entry(ci_id, ip, hostname, os_version, port, user, password):
    return {
        "ci_id": ci_id,
        "ci_dict": {"_type": 52},
        "ip": ip,
        "custom_hostname": hostname,
        "os_version": os_version,
        "ansible_port": port,
        "ansible_user": user,
        "ansible_password": password,
        "initial_password": password,
    }


ENTRIES = {
    1: _entry(1, "10.54.6.35", "56-FMS-Tomcat01", "Debian 12.8", 2022, "rdcadmin", "Eve300014!"),
    2: _entry(2, "10.54.6.36", "56-FMS-Tomcat02", "Debian 12.8", 2022, "rdcadmin", "Eve300014!"),
    3: _entry(3, "10.54.40.174", "56-FMS-DB", "Oracle Linux 8.10", 22, "root", "eve.1234"),
}


def _patch(monkeypatch, mod, executor_result):
    monkeypatch.setattr(mod, "_get_db_config", lambda: {})
    monkeypatch.setattr(mod.AnsibleSync, "_build_host_entry", lambda self, ci_id: ENTRIES[ci_id])
    monkeypatch.setattr(mod.AnsibleClient, "run_playbook", lambda self, **kwargs: executor_result)
    saved = []
    monkeypatch.setattr(mod.AnsibleSync, "_save_ci_password",
                        lambda self, ci_id, ci_dict, new_password: saved.append(ci_id))
    return saved


def test_setup_servers_batch_uses_per_host_status(ansible_mod, monkeypatch):
    executor_result = {
        "status": "Partial",
        "returncode": 4,
        "host_results": {
            "10.54.6.35": "Success",
            "10.54.6.36": "Success",
            "10.54.40.174": "Failed",
        },
        "stdout": "PLAY RECAP ...",
        "stderr": "",
    }
    saved = _patch(monkeypatch, ansible_mod, executor_result)

    with _app().app_context():
        result = ansible_mod.AnsibleSync().setup_servers_batch(
            [1, 2, 3], playbook="setup_server.yml", new_password="new-pass")

    assert result["status"] == "Partial"
    assert [h["status"] for h in result["hosts_result"]] == ["Success", "Success", "Failed"]
    assert [h["ip"] for h in result["hosts_result"]] == ["10.54.6.35", "10.54.6.36", "10.54.40.174"]
    assert saved == [1, 2]


def test_setup_servers_batch_falls_back_to_overall_status(ansible_mod, monkeypatch):
    executor_result = {
        "status": "Failed",
        "returncode": 4,
        "stdout": "",
        "stderr": "",
    }
    saved = _patch(monkeypatch, ansible_mod, executor_result)

    with _app().app_context():
        result = ansible_mod.AnsibleSync().setup_servers_batch([1, 2], playbook="setup_server.yml")

    assert result["status"] == "Failed"
    assert [h["status"] for h in result["hosts_result"]] == ["Failed", "Failed"]
    assert saved == []


def test_setup_server_uses_host_result_status(ansible_mod, monkeypatch):
    executor_result = {
        "status": "Failed",
        "returncode": 4,
        "host_results": {"10.54.6.35": "Success"},
        "stdout": "",
        "stderr": "",
    }
    saved = _patch(monkeypatch, ansible_mod, executor_result)

    with _app().app_context():
        result = ansible_mod.AnsibleSync().setup_server(
            1, playbook="setup_server.yml", new_password="new-pass")

    assert result["status"] == "Success"
    assert saved == [1]


def test_setup_server_keeps_failed_status(ansible_mod, monkeypatch):
    executor_result = {
        "status": "Failed",
        "returncode": 4,
        "host_results": {"10.54.6.35": "Failed"},
        "stdout": "",
        "stderr": "",
    }
    saved = _patch(monkeypatch, ansible_mod, executor_result)

    with _app().app_context():
        result = ansible_mod.AnsibleSync().setup_server(
            1, playbook="setup_server.yml", new_password="new-pass")

    assert result["status"] == "Failed"
    assert saved == []
