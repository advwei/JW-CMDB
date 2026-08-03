# -*- coding:utf-8 -*-

from flask import abort
from flask import request

from api.lib.cmdb.jumpserver import JumpServerAssetSync
from api.lib.cmdb.jumpserver import JumpServerConfigError
from api.lib.utils import get_page_size
from api.resource import APIView


class JumpServerCISyncView(APIView):
    url_prefix = '/jumpserver/sync/ci/<int:ci_id>'

    def post(self, ci_id):
        payload = request.get_json(silent=True) or {}
        update_ci = payload.get('update_ci', request.values.get('update_ci', True))
        if isinstance(update_ci, str):
            update_ci = update_ci not in ('false', 'False', '0', 'no', 'NO')

        try:
            result = JumpServerAssetSync().sync_ci(ci_id, update_ci=update_ci)
        except JumpServerConfigError as e:
            return abort(400, str(e))

        return self.jsonify(result)


class JumpServerQuerySyncView(APIView):
    url_prefix = '/jumpserver/sync'

    def post(self):
        payload = request.get_json(silent=True) or {}
        query = payload.get('q') or request.values.get('q')
        if not query:
            return abort(400, 'q is required')

        count = get_page_size(payload.get('count') or request.values.get('count') or 100000)

        try:
            result, errors = JumpServerAssetSync().sync_query(query, count=count)
        except JumpServerConfigError as e:
            return abort(400, str(e))

        return self.jsonify(total=len(result),
                            failed=len(errors),
                            result=result,
                            errors=errors)
