# -*- coding:utf-8 -*-

from flask import request

from api.lib.cmdb.custom_dashboard import SystemConfigManager
from api.resource import APIView


class ModelConfigView(APIView):
    url_prefix = '/model/config'

    def get(self):
        config = SystemConfigManager.get('model_config')
        default = {'vmserver_type_id': 52, 'delserver_type_id': 54}
        return self.jsonify(config.get('option') if config else default)

    def post(self):
        payload = request.get_json(silent=True) or {}
        SystemConfigManager.create_or_update('model_config', payload)
        return self.jsonify(payload)
