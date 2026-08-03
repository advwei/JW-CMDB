# -*- coding:utf-8 -*-

import json

import requests
from flask import abort
from flask import current_app

from api.lib.cmdb.ci import CIManager
from api.lib.cmdb.const import RetKey
from api.lib.cmdb.search import SearchError
from api.lib.cmdb.search.ci import search as ci_search


class JumpServerConfigError(Exception):
    pass


def _get_db_config():
    from api.lib.cmdb.custom_dashboard import SystemConfigManager
    config = SystemConfigManager.get('jms_config')
    return (config or {}).get('option') or {}


class JumpServerClient(object):
    def __init__(self):
        db_config = _get_db_config()
        self.base_url = (db_config.get('JMS_URL') or current_app.config.get('JMS_URL') or '').rstrip('/')
        self.token = db_config.get('JMS_TOKEN') or current_app.config.get('JMS_TOKEN') or ''
        self.timeout = db_config.get('JMS_TIMEOUT') or current_app.config.get('JMS_TIMEOUT') or 10

        if not self.base_url or not self.token:
            raise JumpServerConfigError('JMS_URL or JMS_TOKEN is not configured')

    @property
    def headers(self):
        return {
            'Authorization': 'Token {}'.format(self.token),
            'Content-Type': 'application/json',
        }

    def _url(self, path):
        if self.base_url.endswith('/api/v1'):
            return '{}{}'.format(self.base_url, path)

        return '{}/api/v1{}'.format(self.base_url, path)

    def create_host(self, payload):
        response = requests.post(self._url('/assets/hosts/'),
                                 headers=self.headers,
                                 json=payload,
                                 timeout=self.timeout)
        return self._handle_response(response, expected=(200, 201))

    def update_host(self, asset_id, payload):
        response = requests.patch(self._url('/assets/hosts/{}/'.format(asset_id)),
                                  headers=self.headers,
                                  json=payload,
                                  timeout=self.timeout)
        return self._handle_response(response, expected=(200, 201))

    def delete_host(self, asset_id):
        current_app.logger.info('JumpServer delete_host: calling DELETE /assets/hosts/{}/'.format(asset_id))
        response = requests.delete(self._url('/assets/hosts/{}/'.format(asset_id)),
                                   headers=self.headers,
                                   timeout=self.timeout)
        current_app.logger.info('JumpServer delete_host: response status={}, body={}'.format(
            response.status_code, response.text[:500] if response.text else ''))
        return self._handle_response(response, expected=(200, 204))

    @staticmethod
    def _handle_response(response, expected):
        if response.status_code not in expected:
            raise Exception('JumpServer request failed: status={}, body={}'.format(response.status_code,
                                                                                  response.text))
        if response.text:
            return response.json()

        return {}


class JumpServerAssetSync(object):
    DEFAULT_FIELD_MAP = {
        'name': ['assetname', 'hostname', 'name'],
        'address': ['ip', 'private_ip', 'public_ip', 'address'],
        'platform': ['os_type', 'platform', 'ostype'],
        'protocol': ['os_version', 'protocol'],
        'node': ['node_name', 'jms_node', 'node', 'jmasset'],
        'secret': ['password', 'secret'],
        'asset_id': ['jumpserver_id', 'jms_asset_id'],
    }

    def __init__(self):
        self.client = JumpServerClient()
        self._db_config = _get_db_config()
        self.field_map = self._load_mapping('JMS_FIELD_MAP', self.DEFAULT_FIELD_MAP)
        self.node_map = self._db_config.get('JMS_NODE_MAP') or current_app.config.get('JMS_NODE_MAP') or {}
        self.platform_map = self._db_config.get('JMS_PLATFORM_MAP') or current_app.config.get('JMS_PLATFORM_MAP') or {}
        self.protocol_map = self._db_config.get('JMS_PROTOCOL_MAP') or current_app.config.get('JMS_PROTOCOL_MAP') or {}
        self._db_default_node_id = self._db_config.get('JMS_DEFAULT_NODE_ID') or ''
        self._db_default_account_secret = self._db_config.get('JMS_DEFAULT_ACCOUNT_SECRET') or ''
        self._db_account_name = self._db_config.get('JMS_ACCOUNT_NAME') or ''
        self._db_account_username = self._db_config.get('JMS_ACCOUNT_USERNAME') or ''

    @staticmethod
    def _load_mapping(config_key, default):
        mapping = current_app.config.get(config_key) or {}
        if isinstance(mapping, str):
            mapping = json.loads(mapping or '{}')

        result = default.copy()
        result.update(mapping)
        return result

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

    def _platform(self, ci_dict):
        raw = self._first_value(ci_dict, self.field_map.get('platform'))
        return self.platform_map.get(raw, raw or self.platform_map.get('default'))

    def _protocols(self, ci_dict):
        raw = self._first_value(ci_dict, self.field_map.get('protocol'))
        configured = self.protocol_map.get(raw) or self.protocol_map.get('default')
        if configured:
            return configured

        return [{'name': 'ssh', 'port': 22}]

    def _nodes(self, ci_dict):
        raw = self._first_value(ci_dict, self.field_map.get('node'))
        default_node_id = self._db_default_node_id or current_app.config.get('JMS_DEFAULT_NODE_ID')
        node_id = self.node_map.get(raw, raw) or default_node_id
        if not node_id:
            raise JumpServerConfigError('JumpServer node is missing, configure JMS_DEFAULT_NODE_ID or JMS_NODE_MAP')

        return [node_id]

    def build_payload(self, ci_dict):
        name = self._first_value(ci_dict, self.field_map.get('name'))
        address = self._first_value(ci_dict, self.field_map.get('address'))
        platform = self._platform(ci_dict)
        default_secret = self._db_default_account_secret or current_app.config.get('JMS_DEFAULT_ACCOUNT_SECRET')
        secret = self._first_value(ci_dict, self.field_map.get('secret')) or default_secret

        if not name:
            raise JumpServerConfigError('JumpServer asset name is missing')
        if not address:
            raise JumpServerConfigError('JumpServer asset address is missing')
        if not platform:
            raise JumpServerConfigError('JumpServer asset platform is missing')

        payload = {
            'name': name,
            'address': address,
            'platform': platform,
            'protocols': self._protocols(ci_dict),
            'nodes': self._nodes(ci_dict),
        }

        account_name = self._db_account_name or current_app.config.get('JMS_ACCOUNT_NAME') or 'default'
        account_username = self._db_account_username or current_app.config.get('JMS_ACCOUNT_USERNAME') or 'root'
        if secret:
            payload['accounts'] = [{
                'name': account_name,
                'username': account_username,
                'secret': secret,
                'secret_type': 'password',
            }]

        return payload

    def sync_ci(self, ci_id, update_ci=True):
        ci_dict = CIManager.get_ci_by_id_from_db(ci_id,
                                                 ret_key=RetKey.NAME,
                                                 need_children=False,
                                                 valid=True)
        payload = self.build_payload(ci_dict)
        existed_asset_id = self._first_value(ci_dict, self.field_map.get('asset_id'))

        if existed_asset_id:
            result = self.client.update_host(existed_asset_id, payload)
            action = 'updated'
        else:
            result = self.client.create_host(payload)
            action = 'created'

        self._write_back_asset_id(ci_id, result, update_ci=update_ci)

        return {
            'ci_id': ci_id,
            'action': action,
            'asset': {
                'id': result.get('id'),
                'name': result.get('name'),
                'address': result.get('address'),
                'nodes_display': result.get('nodes_display'),
            }
        }

    def sync_query(self, query, count=100000):
        try:
            response, _, _, _, _, _ = ci_search(query,
                                                ret_key=RetKey.NAME,
                                                count=count,
                                                use_ci_filter=True).search()
        except SearchError as e:
            return abort(400, str(e))

        result = []
        errors = []
        for ci in response:
            ci_id = ci.get('_id')
            try:
                result.append(self.sync_ci(ci_id))
            except Exception as e:
                current_app.logger.exception('sync ci {} to JumpServer failed'.format(ci_id))
                errors.append({'ci_id': ci_id, 'error': str(e)})

        return result, errors

    def delete_ci(self, ci_id):
        current_app.logger.info('JumpServer delete_ci: ci_id={}'.format(ci_id))
        ci_dict = CIManager.get_ci_by_id_from_db(ci_id,
                                                 ret_key=RetKey.NAME,
                                                 need_children=False,
                                                 valid=True)
        current_app.logger.info('JumpServer delete_ci: ci_dict keys={}'.format(list(ci_dict.keys()) if ci_dict else None))
        asset_id = self._first_value(ci_dict, self.field_map.get('asset_id'))
        current_app.logger.info('JumpServer delete_ci: asset_id={}, field_map asset_id={}'.format(
            asset_id, self.field_map.get('asset_id')))
        if not asset_id:
            current_app.logger.info('JumpServer delete_ci: no asset_id found, skipping ci_id={}'.format(ci_id))
            return None

        current_app.logger.info('JumpServer delete_ci: calling delete_host for asset_id={}'.format(asset_id))
        self.client.delete_host(asset_id)
        current_app.logger.info('JumpServer delete_ci: asset deleted successfully, ci_id={}, asset_id={}'.format(ci_id, asset_id))
        return {'ci_id': ci_id, 'asset_id': asset_id, 'action': 'deleted'}

    def _write_back_asset_id(self, ci_id, result, update_ci=True):
        asset_id = result.get('id')
        asset_id_field = self.field_map.get('asset_id')
        if not update_ci or not asset_id or not asset_id_field:
            return

        if isinstance(asset_id_field, list):
            asset_id_field = asset_id_field[0]

        try:
            CIManager().update(ci_id,
                               _is_admin=True,
                               _sync=True,
                               **{asset_id_field: asset_id})
        except Exception as e:
            current_app.logger.warning('write JumpServer asset id back to ci {} failed: {}'.format(ci_id, e))
