from flask import abort, session
from flask import current_app
from flask import request

from api.lib.cmdb.ansible import AnsibleSync
from api.lib.cmdb.ansible import AnsibleConfigError
from api.lib.cmdb.custom_dashboard import SystemConfigManager
from api.extensions import db
from api.models.ansible import AnsibleExecution, AnsibleExecutionDetail
from api.resource import APIView


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

        try:
            result = AnsibleSync().setup_server(ci_id, playbook=playbook, new_password=new_password, extra_params=extra_params or None)
        except AnsibleConfigError as e:
            execution.update(status='Failed')
            db.session.commit()
            return abort(400, str(e))
        except Exception as e:
            current_app.logger.exception('Ansible setup-server failed: ci_id={}'.format(ci_id))
            execution.update(status='Failed', success_count=0, failed_count=1)
            AnsibleExecutionDetail.create(
                execution_id=execution.id,
                ci_id=ci_id,
                ci_name='',
                ip='',
                status='Failed',
                returncode=-1,
                stdout='',
                stderr=str(e),
            )
            db.session.commit()
            return abort(500, str(e))

        exec_status = 'Success' if result.get('status') == 'Success' else 'Failed'
        execution.update(
            status=exec_status,
            success_count=1 if exec_status == 'Success' else 0,
            failed_count=0 if exec_status == 'Success' else 1,
        )
        AnsibleExecutionDetail.create(
            execution_id=execution.id,
            ci_id=ci_id,
            ci_name=result.get('hostname', ''),
            ip=result.get('ip', ''),
            status=exec_status,
            returncode=result.get('returncode'),
            stdout=result.get('stdout', ''),
            stderr=result.get('stderr', ''),
        )
        db.session.commit()

        return self.jsonify(result)


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

        try:
            batch_result = AnsibleSync().setup_servers_batch(
                ci_ids, playbook=playbook, new_password=new_password, extra_params=extra_params or None
            )
        except Exception as e:
            current_app.logger.exception('Ansible batch setup failed')
            execution.update(status='Failed', success_count=0, failed_count=len(ci_ids))
            AnsibleExecutionDetail.create(
                execution_id=execution.id,
                ci_id=ci_ids[0] if ci_ids else 0,
                ci_name='',
                ip='',
                status='Failed',
                returncode=-1,
                stdout='',
                stderr=str(e),
            )
            db.session.commit()
            return abort(500, str(e))

        exec_status = batch_result.get('status', 'Failed')
        success_count = sum(1 for h in batch_result.get('hosts_result', []) if h.get('status') == 'Success')
        failed_count = len(batch_result.get('errors', [])) + (len(batch_result.get('hosts_result', [])) - success_count)

        execution.update(
            status=exec_status,
            success_count=success_count,
            failed_count=failed_count,
        )

        for h in batch_result.get('hosts_result', []):
            AnsibleExecutionDetail.create(
                execution_id=execution.id,
                ci_id=h.get('ci_id', 0),
                ci_name=h.get('hostname', ''),
                ip=h.get('ip', ''),
                status=h.get('status', exec_status),
                returncode=batch_result.get('returncode'),
                stdout=batch_result.get('stdout', ''),
                stderr=batch_result.get('stderr', ''),
            )

        for err in batch_result.get('errors', []):
            AnsibleExecutionDetail.create(
                execution_id=execution.id,
                ci_id=err.get('ci_id', 0),
                ci_name='',
                ip='',
                status='Failed',
                returncode=-1,
                stdout='',
                stderr=err.get('error', ''),
            )

        db.session.commit()

        return self.jsonify(
            total=len(batch_result.get('hosts_result', [])) + len(batch_result.get('errors', [])),
            failed=failed_count,
            result=batch_result.get('hosts_result', []),
            errors=batch_result.get('errors', []),
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
