from pathlib import Path

import executor as ex


def parse_inventory(text):
    sections = {}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
            sections.setdefault(current, [])
        elif current is not None and stripped:
            sections[current].append(stripped)
    return sections


def sample_stdout(failed_ip, ok_ips):
    lines = [
        "PLAY [批量初始化服务器配置（主机名与密码）] ************************************",
        "",
        "TASK [Gathering Facts] *********************************************************",
    ]
    for ip in ok_ips:
        lines.append(f"ok: [{ip}]")
    lines.append(f'fatal: [{failed_ip}]: UNREACHABLE! => {{"changed": false, "unreachable": true}}')
    lines.append("")
    lines.append("PLAY RECAP *********************************************************************")
    for ip in ok_ips:
        lines.append(f"{ip:<26}: ok=4    changed=3    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0")
    lines.append(f"{failed_ip:<26}: ok=0    changed=0    unreachable=1    failed=0    skipped=0    rescued=0    ignored=0")
    return "\n".join(lines)


def ok_stdout(ips):
    lines = [
        "PLAY [批量初始化服务器配置（主机名与密码）] ************************************",
        "",
        "TASK [Gathering Facts] *********************************************************",
    ]
    lines.extend(f"ok: [{ip}]" for ip in ips)
    lines.append("")
    lines.append("PLAY RECAP *********************************************************************")
    lines.extend(
        f"{ip:<26}: ok=4    changed=3    unreachable=0    failed=0    skipped=1    rescued=0    ignored=0"
        for ip in ips
    )
    return "\n".join(lines)


def make_hosts():
    return [
        {"ip": "10.54.4.101", "custom_hostname": "host-101", "os_version": "Debian 12.8",
         "ansible_port": 2022, "ansible_user": "rdcadmin", "ansible_password": "Eve300014!"},
        {"ip": "10.54.4.102", "custom_hostname": "host-102", "os_version": "Oracle Linux 8.10",
         "ansible_port": 22, "ansible_user": "root", "ansible_password": "eve.1234"},
        {"ip": "10.54.4.103", "custom_hostname": "host-103", "os_version": "Debian 12.8",
         "ansible_port": 2022, "ansible_user": "rdcadmin", "ansible_password": "Eve300014!"},
    ]


class FakeCompleted:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_inventory_splits_linux_hosts_by_os_version():
    inventory = parse_inventory(ex.build_inventory(make_hosts()))

    assert inventory["linux_debian_12_8"] == [
        "10.54.4.101 custom_hostname=host-101 ansible_password=Eve300014!",
        "10.54.4.103 custom_hostname=host-103 ansible_password=Eve300014!",
    ]
    assert inventory["linux_debian_12_8:vars"] == [
        "ansible_port=2022",
        "ansible_user=rdcadmin",
        "ansible_connection=ssh",
    ]
    assert inventory["linux_oracle_linux_8_10:vars"] == [
        "ansible_port=22",
        "ansible_user=root",
        "ansible_connection=ssh",
    ]
    assert inventory["linux:children"] == ["linux_debian_12_8", "linux_oracle_linux_8_10"]
    assert inventory["targethost:children"] == ["linux"]
    assert inventory["targethost:vars"] == ["ansible_python_interpreter=/usr/bin/python3"]
    assert "linux" not in inventory
    assert "linux:vars" not in inventory


def test_build_inventory_windows_hosts_use_windows_credentials():
    hosts = [{
        "ip": "10.54.6.33",
        "custom_hostname": "56-FMS-ECS-1",
        "os_version": "Windows Server 2019",
        "ansible_port": 5985,
        "ansible_user": "Administrator",
        "ansible_password": "eve.1234",
    }]
    inventory = parse_inventory(ex.build_inventory(hosts))

    assert inventory["windows_server_2019"] == [
        "10.54.6.33 custom_hostname=56-FMS-ECS-1 ansible_password=eve.1234",
    ]
    assert inventory["windows_server_2019:vars"] == [
        "ansible_port=5985",
        "ansible_user=Administrator",
        "ansible_winrm_transport=ntlm",
        "ansible_winrm_server_cert_validation=ignore",
        "ansible_connection=winrm",
    ]
    assert inventory["windows:children"] == ["windows_server_2019"]
    assert inventory["targethost:children"] == ["windows"]


def test_build_inventory_keeps_both_platform_children():
    hosts = make_hosts() + [{
        "ip": "10.54.6.33",
        "custom_hostname": "56-FMS-ECS-1",
        "os_version": "Windows Server 2019",
        "ansible_port": 5985,
        "ansible_user": "Administrator",
        "ansible_password": "eve.1234",
    }]
    inventory = parse_inventory(ex.build_inventory(hosts))

    assert inventory["targethost:children"] == ["linux", "windows"]


def test_build_inventory_extra_params_are_kept():
    inventory = parse_inventory(ex.build_inventory(make_hosts(), {"new_password": "u&eRIk9{YH+&"}))

    assert "new_password=u&eRIk9{YH+&" in inventory["targethost:vars"]


def test_parse_play_recap_reports_each_host():
    ok_ips = [f"10.54.4.{i}" for i in range(101, 127)]
    stdout = sample_stdout("10.54.4.127", ok_ips)

    recap = ex.parse_play_recap(stdout)

    assert len(recap) == 27
    assert recap["10.54.4.101"] == {
        "ok": 4, "changed": 3, "unreachable": 0, "failed": 0, "skipped": 1, "rescued": 0, "ignored": 0,
    }
    assert recap["10.54.4.127"]["unreachable"] == 1


def test_build_host_results_marks_only_failed_host():
    ok_ips = [f"10.54.4.{i}" for i in range(101, 127)]
    stdout = sample_stdout("10.54.4.127", ok_ips)
    hosts = [{"ip": ip} for ip in ok_ips + ["10.54.4.127"]]

    host_results = ex.build_host_results(hosts, stdout, 4)

    assert host_results["10.54.4.127"] == "Failed"
    assert {host_results[ip] for ip in ok_ips} == {"Success"}
    assert ex.summarize_status(host_results.values(), 4) == "Partial"


def test_summarize_status():
    assert ex.summarize_status(["Success", "Success"], 0) == "Success"
    assert ex.summarize_status(["Failed", "Failed"], 4) == "Failed"
    assert ex.summarize_status(["Success", "Failed"], 4) == "Partial"
    assert ex.summarize_status([], 4) == "Failed"
    assert ex.summarize_status([], 0) == "Success"


def test_build_host_results_falls_back_to_returncode_without_recap():
    hosts = make_hosts()

    assert ex.build_host_results(hosts, "fatal: syntax error", 4) == {
        "10.54.4.101": "Failed",
        "10.54.4.102": "Failed",
        "10.54.4.103": "Failed",
    }
    assert ex.summarize_status([ex.STATUS_FAILED] * 3, 4) == "Failed"


def _prepare_paths(tmp_path, monkeypatch):
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "setup_server.yml").write_text("---\n", encoding="utf-8")
    inventory_dir = tmp_path / "inventory"
    inventory_dir.mkdir()

    monkeypatch.setattr(ex, "ANSIBLE_PLAYBOOK_DIR", playbook_dir)
    monkeypatch.setattr(ex, "ANSIBLE_INVENTORY_DIR", inventory_dir)
    monkeypatch.setattr(ex, "ANSIBLE_TIMEOUT", 5)
    return inventory_dir


def test_run_playbook_returns_partial_when_one_host_fails(tmp_path, monkeypatch):
    inventory_dir = _prepare_paths(tmp_path, monkeypatch)
    stdout = sample_stdout("10.54.4.103", ["10.54.4.101", "10.54.4.102"])
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["inventory"] = Path(cmd[2]).read_text(encoding="utf-8")
        return FakeCompleted(4, stdout)

    monkeypatch.setattr(ex.subprocess, "run", fake_run)

    result = ex.run_playbook(hosts=make_hosts(), playbook="setup_server.yml")

    assert result["status"] == "Partial"
    assert result["host_results"] == {
        "10.54.4.101": "Success",
        "10.54.4.102": "Success",
        "10.54.4.103": "Failed",
    }
    assert "ansible_port=2022" in captured["inventory"]
    assert "ansible_user=rdcadmin" in captured["inventory"]
    assert list(inventory_dir.iterdir()) == []


def test_run_playbook_returns_success_when_all_hosts_ok(tmp_path, monkeypatch):
    _prepare_paths(tmp_path, monkeypatch)
    stdout = ok_stdout(["10.54.4.101", "10.54.4.102", "10.54.4.103"])

    monkeypatch.setattr(ex.subprocess, "run", lambda *args, **kwargs: FakeCompleted(0, stdout))

    result = ex.run_playbook(hosts=make_hosts(), playbook="setup_server.yml")

    assert result["status"] == "Success"
    assert set(result["host_results"].values()) == {"Success"}


def test_run_playbook_timeout_marks_all_hosts_failed(tmp_path, monkeypatch):
    _prepare_paths(tmp_path, monkeypatch)

    def fake_run(cmd, **kwargs):
        raise ex.subprocess.TimeoutExpired(cmd=cmd, timeout=5)

    monkeypatch.setattr(ex.subprocess, "run", fake_run)

    result = ex.run_playbook(hosts=make_hosts(), playbook="setup_server.yml")

    assert result["status"] == "Failed"
    assert result["host_results"] == {}
