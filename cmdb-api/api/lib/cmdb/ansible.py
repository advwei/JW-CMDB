import json

import requests
from flask import current_app

from api.lib.cmdb.ci import CIManager
from api.lib.cmdb.const import RetKey
from api.lib.cmdb.cache import AttributeCache

WINDOWS_KEYWORDS = {"windows", "win", "windows server", "windows_server"}


class AnsibleConfigError(Exception):
    pass


def _get_db_config():
    from api.lib.cmdb.custom_dashboard import SystemConfigManager
    config = SystemConfigManager.get('ansible_config')
    return (config or {}).get('option') or {}


def is_windows_os(os_version):
    if not os_version:
        return False
    return any(kw in os_version.lower() for kw in WINDOWS_KEYWORDS)


class AnsibleClient(object):
    def __init__(self):
        db_config = _get_db_config()
        self.executor_url = (db_config.get('executor_url') or current_app.config.get('ANSIBLE_EXECUTOR_URL') or '').rstrip('/')
        self.api_key = db_config.get('executor_api_key') or current_app.config.get('ANSIBLE_EXECUTOR_API_KEY') or ''
        self.timeout = db_config.get('timeout') or current_app.config.get('ANSIBLE_TIMEOUT') or 600

        if not self.executor_url:
            raise AnsibleConfigError('Ansible executor URL is not configured')

    @property
    def headers(self):
        return {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json',
        }

    def run_playbook(self, hosts, playbook, new_password=None, extra_params=None):
        payload = {
            'hosts': hosts,
            'playbook': playbook,
        }
        if new_password:
            payload['new_password'] = new_password
        if extra_params:
            payload['extra_params'] = extra_params

        response = requests.post(
            '{}/api/exec/run-playbook'.format(self.executor_url),
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            try:
                detail = response.json().get('error') or response.text
            except Exception:
                detail = response.text
            raise Exception('Ansible executor request failed: status={}, detail={}'.format(
                response.status_code, detail))
        return response.json()

    def list_playbooks(self):
        response = requests.get(
            '{}/api/exec/playbooks'.format(self.executor_url),
            headers=self.headers,
            timeout=10,
        )
        if response.status_code != 200:
            raise Exception('Failed to list playbooks: status={}, body={}'.format(
                response.status_code, response.text))
        return response.json().get('playbooks', [])


class AnsibleSync(object):
    DEFAULT_FIELD_MAP = {
        'ip': ['ip', 'private_ip', 'public_ip', 'address'],
        'hostname': ['hostname', 'name', 'assetname'],
        'os_version': ['os_version', 'os', 'ostype', 'platform'],
        'password': ['password', 'root_password', 'admin_password', 'ssh_password'],
    }

    def __init__(self):
        self.client = AnsibleClient()
        self._db_config = _get_db_config()
        self.field_map = self._load_mapping('field_map', self.DEFAULT_FIELD_MAP)
        self.os_credentials = self._db_config.get('os_credentials') or current_app.config.get('ANSIBLE_OS_CREDENTIALS') or []
        self.default_playbook = self._db_config.get('default_playbook') or current_app.config.get('ANSIBLE_DEFAULT_PLAYBOOK') or 'setup_server.yml'

    @staticmethod
    def _load_mapping(config_key, default):
        db_config = _get_db_config()
        mapping = db_config.get(config_key) or {}
        if isinstance(mapping, str):
            mapping = json.loads(mapping or '{}')
        result = default.copy()
        result.update(mapping)
        return result

    @staticmethod
    def _is_initial_setup(playbook):
        if not playbook:
            return False
        return playbook.replace('\\', '/').split('/')[-1] == 'setup_server.yml'

    @staticmethod
    def _first_value(ci_dict, candidates):
        if isinstance(candidates, str):
            candidates = [candidates]
        for key in candidates:
            value = ci_dict.get(key)
            if value is not None and value != '':
                if isinstance(value, list):
                    return value[0] if value else None
                return value
        return None

    def _get_credentials(self, os_version):
        if is_windows_os(os_version):
            default = {'ansible_port': 5985, 'ansible_user': 'Administrator', 'ansible_password': ''}
        else:
            default = {'ansible_port': 22, 'ansible_user': 'root', 'ansible_password': 'eve.1234'}

        creds = self.os_credentials
        if isinstance(creds, list):
            for entry in creds:
                if entry.get('os') == os_version:
                    return {
                        'ansible_port': entry.get('port', default['ansible_port']),
                        'ansible_user': entry.get('user', default['ansible_user']),
                        'ansible_password': entry.get('password', default['ansible_password']),
                    }

        fallback_key = 'Windows' if is_windows_os(os_version) else 'Linux'
        if isinstance(creds, list):
            for entry in creds:
                if entry.get('os') == fallback_key or entry.get('os') == 'default':
                    return {
                        'ansible_port': entry.get('port', default['ansible_port']),
                        'ansible_user': entry.get('user', default['ansible_user']),
                        'ansible_password': entry.get('password', default['ansible_password']),
                    }

        return default

    def _get_password_attr_id(self, ci_dict):
        candidates = self.field_map.get('password', ['password'])
        for name in candidates:
            if name in ci_dict:
                attr = AttributeCache.get(name)
                if attr and attr.is_password:
                    return attr.id
        return None

    def _get_ci_password(self, ci_id, ci_dict):
        attr_id = self._get_password_attr_id(ci_dict)
        if attr_id is not None:
            return CIManager.load_password(ci_id, attr_id)
        return None

    def _save_ci_password(self, ci_id, ci_dict, new_password):
        attr_id = self._get_password_attr_id(ci_dict)
        if attr_id is not None:
            type_id = ci_dict.get('_type')
            if type_id:
                CIManager.save_password(ci_id, attr_id, (new_password, False), None, type_id)
                return True
        return False

    def _build_host_entry(self, ci_id):
        ci_dict = CIManager.get_ci_by_id_from_db(ci_id,
                                                 ret_key=RetKey.NAME,
                                                 need_children=False,
                                                 valid=True)
        ip = self._first_value(ci_dict, self.field_map.get('ip'))
        hostname = self._first_value(ci_dict, self.field_map.get('hostname'))
        os_version = self._first_value(ci_dict, self.field_map.get('os_version'))

        if not ip:
            raise AnsibleConfigError('CI {} has no IP address (checked: {})'.format(
                ci_id, self.field_map.get('ip')))
        if not hostname:
            raise AnsibleConfigError('CI {} has no hostname (checked: {})'.format(
                ci_id, self.field_map.get('hostname')))

        creds = self._get_credentials(os_version)
        ci_password = self._get_ci_password(ci_id, ci_dict)

        return {
            'ci_id': ci_id,
            'ci_dict': ci_dict,
            'ip': ip,
            'custom_hostname': hostname,
            'os_version': os_version or '',
            'ansible_port': creds['ansible_port'],
            'ansible_user': creds['ansible_user'],
            'ansible_password': ci_password or creds['ansible_password'],
            'initial_password': creds['ansible_password'],
        }

    def setup_server(self, ci_id, playbook=None, new_password=None, extra_params=None):
        entry = self._build_host_entry(ci_id)
        playbook = playbook or self.default_playbook

        use_initial = self._is_initial_setup(playbook) and bool(new_password)
        ansible_password = entry['initial_password'] if use_initial else entry['ansible_password']
        current_app.logger.info(
            'Ansible setup_server: ci_id={} playbook={} new_password_provided={} use_initial={} '
            'password_source={}'.format(
                ci_id, playbook, bool(new_password), use_initial,
                'initial' if use_initial else 'ci_or_default'))

        hosts = [{
            'ip': entry['ip'],
            'custom_hostname': entry['custom_hostname'],
            'os_version': entry['os_version'],
            'ansible_port': entry['ansible_port'],
            'ansible_user': entry['ansible_user'],
            'ansible_password': ansible_password,
        }]

        result = self.client.run_playbook(
            hosts=hosts,
            playbook=playbook,
            new_password=new_password,
            extra_params=extra_params,
        )

        if new_password and result.get('status') == 'Success':
            self._save_ci_password(ci_id, entry['ci_dict'], new_password)

        return {
            'ci_id': ci_id,
            'ip': entry['ip'],
            'hostname': entry['custom_hostname'],
            'os_version': entry['os_version'],
            'playbook': playbook,
            'status': result.get('status'),
            'returncode': result.get('returncode'),
            'stdout': result.get('stdout'),
            'stderr': result.get('stderr'),
        }

    def setup_servers_batch(self, ci_ids, playbook=None, new_password=None, extra_params=None):
        playbook = playbook or self.default_playbook
        use_initial = self._is_initial_setup(playbook) and bool(new_password)
        current_app.logger.info(
            'Ansible setup_servers_batch: ci_ids={} playbook={} new_password_provided={} use_initial={}'.format(
                ci_ids, playbook, bool(new_password), use_initial))
        hosts = []
        host_entries = {}
        errors = []

        for ci_id in ci_ids:
            try:
                entry = self._build_host_entry(ci_id)
                hosts.append({
                    'ip': entry['ip'],
                    'custom_hostname': entry['custom_hostname'],
                    'os_version': entry['os_version'],
                    'ansible_port': entry['ansible_port'],
                    'ansible_user': entry['ansible_user'],
                    'ansible_password': entry['initial_password'] if use_initial else entry['ansible_password'],
                })
                host_entries[entry['ip']] = entry
            except Exception as e:
                errors.append({'ci_id': ci_id, 'error': str(e)})

        if not hosts:
            return {
                'status': 'Failed',
                'hosts_result': [],
                'errors': errors,
            }

        result = self.client.run_playbook(
            hosts=hosts,
            playbook=playbook,
            new_password=new_password,
            extra_params=extra_params,
        )

        hosts_result = []
        for h in hosts:
            entry = host_entries.get(h['ip'], {})
            ci_id = entry.get('ci_id')
            if ci_id and new_password and result.get('status') == 'Success':
                self._save_ci_password(ci_id, entry.get('ci_dict', {}), new_password)
            hosts_result.append({
                'ci_id': ci_id,
                'ip': h['ip'],
                'hostname': h['custom_hostname'],
                'os_version': h.get('os_version', ''),
                'status': result.get('status'),
            })

        return {
            'status': result.get('status'),
            'returncode': result.get('returncode'),
            'stdout': result.get('stdout'),
            'stderr': result.get('stderr'),
            'playbook': playbook,
            'hosts_result': hosts_result,
            'errors': errors,
        }
