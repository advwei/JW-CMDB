# -*- coding:utf-8 -*-

import secrets

from flask import request

from api.lib.cmdb.custom_dashboard import SystemConfigManager
from api.lib.common_setting.decorator import perms_role_required
from api.lib.common_setting.role_perm_base import CMDBApp
from api.resource import APIView

app_cli = CMDBApp()

CONFIG_NAME = 'agent_config'


class AgentConfigView(APIView):
    url_prefix = "/ipam/agent/config"

    @perms_role_required(app_cli.app_name, app_cli.resource_type_name, app_cli.op.IPAM,
                         app_cli.op.read, app_cli.admin_name)
    def get(self):
        cfg = SystemConfigManager.get(CONFIG_NAME)
        return self.jsonify(cfg.get('option') if cfg else {"agents": []})

    @perms_role_required(app_cli.app_name, app_cli.resource_type_name, app_cli.op.IPAM,
                         app_cli.op.read, app_cli.admin_name)
    def post(self):
        payload = request.get_json(force=True) if request.is_json else request.values
        SystemConfigManager.create_or_update(CONFIG_NAME, payload)
        return self.jsonify(code=200)


class AgentTokenView(APIView):
    url_prefix = "/ipam/agent/token"

    @perms_role_required(app_cli.app_name, app_cli.resource_type_name, app_cli.op.IPAM,
                         app_cli.op.read, app_cli.admin_name)
    def get(self):
        token = "cmdb_agt_" + secrets.token_hex(16)
        return self.jsonify(token=token)
