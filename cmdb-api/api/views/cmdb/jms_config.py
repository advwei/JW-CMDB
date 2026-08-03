# -*- coding:utf-8 -*-

from flask import request

from api.lib.cmdb.custom_dashboard import SystemConfigManager
from api.resource import APIView


class JMSConfigView(APIView):
    url_prefix = '/jms/config'

    def get(self):
        config = SystemConfigManager.get('jms_config')
        return self.jsonify(config.get('option') if config else {})

    def post(self):
        payload = request.get_json(silent=True) or {}
        SystemConfigManager.create_or_update('jms_config', payload)
        return self.jsonify(payload)
