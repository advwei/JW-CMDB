from flask import abort, session, request

from api.lib.cmdb.ansible import AnsibleConfigError
from api.lib.cmdb.const import CMDB_QUEUE
from api.lib.cmdb.custom_dashboard import SystemConfigManager
from api.extensions import db
from api.models.ansible import AnsibleExecution, AnsibleExecutionDetail
from api.resource import APIView
from api.tasks.ansible import ansible_setup, ansible_batch_setup


class AnsibleSetupView(APIView):
    url_prefix = '/ansible/setup-server/<int:ci_id>'

    def post(self, ci_id):
        payload = request.get_json(silent=True) or {}
        playbook = payload.get('playbook') or request.values.get('playbook')
        new_password = payload.get('new_password') or request.values.get('new_password')
        extra_params_str = payload.get('extra_params') or request.values.get('extra_params') or ''

        extra_params = {}
        if extra_params_str:
            for part in str(extra_params_str).split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    extra_params[k.strip()] = v.strip()

        uid = (session.get("acl") or {}).get("uid", 0)

        execution = AnsibleExecution.create(
            uid=uid,
            playbook=playbook or '',
            ci_ids=[ci_id],
            ci_count=1,
            extra_params={"new_password": bool(new_password), "extra": extra_params},
        )
        db.session.commit()

        ansible_setup.apply_async(
            args=(execution.id, ci_id, playbook or '', new_password or '', extra_params, uid),
            queue=CMDB_QUEUE,
        )

        return self.jsonify(execution_id=execution.id, status=execution.status)


class AnsibleBatchSetupView(APIView):
    url_prefix = '/ansible/setup-server/batch'

    def post(self):
        payload = request.get_json(silent=True) or {}
        ci_ids = payload.get('ci_ids') or request.values.get('ci_ids')
        if not ci_ids:
            return abort(400, 'ci_ids is required')
        if isinstance(ci_ids, str):
            ci_ids = [int(x.strip()) for x in ci_ids.split(',') if x.strip()]

        playbook = payload.get('playbook') or request.values.get('playbook')
        new_password = payload.get('new_password') or request.values.get('new_password')
        extra_params_str = payload.get('extra_params') or request.values.get('extra_params') or ''

        extra_params = {}
        if extra_params_str:
            for part in str(extra_params_str).split():
                if '=' in part:
                    k, v = part.split('=', 1)
                    extra_params[k.strip()] = v.strip()

        uid = (session.get("acl") or {}).get("uid", 0)

        execution = AnsibleExecution.create(
            uid=uid,
            playbook=playbook or '',
            ci_ids=ci_ids,
            ci_count=len(ci_ids),
            extra_params={"new_password": bool(new_password), "extra": extra_params},
        )
        db.session.commit()

        ansible_batch_setup.apply_async(
            args=(execution.id, ci_ids, playbook or '', new_password or '', extra_params, uid),
            queue=CMDB_QUEUE,
        )

        return self.jsonify(
            execution_id=execution.id,
            status=execution.status,
            total=len(ci_ids),
            ci_count=len(ci_ids),
        )


class AnsibleExecutionListView(APIView):
    url_prefix = '/ansible/executions'

    def get(self):
        page = int(request.values.get('page', 1))
        page_size = int(request.values.get('page_size', 20))
        playbook = request.values.get('playbook')
        status = request.values.get('status')

        query = db.session.query(AnsibleExecution)
        if playbook:
            query = query.filter(AnsibleExecution.playbook == playbook)
        if status:
            query = query.filter(AnsibleExecution.status == status)

        total = query.count()
        records = query.order_by(AnsibleExecution.created_at.desc()).offset(
            (page - 1) * page_size).limit(page_size).all()

        return self.jsonify(
            records=[r.to_dict() for r in records],
            total=total,
            page=page,
            page_size=page_size,
        )


class AnsibleExecutionDetailView(APIView):
    url_prefix = '/ansible/executions/<int:execution_id>/details'

    def get(self, execution_id):
        execution = AnsibleExecution.get_by_id(execution_id)
        if not execution:
            return abort(404, 'Execution not found')

        details = db.session.query(AnsibleExecutionDetail).filter(
            AnsibleExecutionDetail.execution_id == execution_id
        ).all()

        return self.jsonify(
            execution=execution.to_dict(),
            details=[d.to_dict() for d in details],
        )


class AnsiblePlaybooksView(APIView):
    url_prefix = '/ansible/playbooks'

    def get(self):
        try:
            from api.lib.cmdb.ansible import AnsibleClient
            playbooks = AnsibleClient().list_playbooks()
        except AnsibleConfigError as e:
            return abort(400, str(e))
        except Exception:
            playbooks = []

        return self.jsonify(playbooks=playbooks)


class AnsibleConfigView(APIView):
    url_prefix = '/ansible/config'

    def get(self):
        config = SystemConfigManager.get('ansible_config')
        return self.jsonify(config.get('option') if config else {})

    def post(self):
        payload = request.get_json(silent=True) or {}
        SystemConfigManager.create_or_update('ansible_config', payload)
        return self.jsonify(payload)
