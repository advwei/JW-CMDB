# -*- coding:utf-8 -*-

from flask import current_app
from flask import has_request_context
from flask_login import login_user

from api.extensions import celery
from api.extensions import db
from api.lib.cmdb.ansible import AnsibleSync
from api.lib.cmdb.const import CMDB_QUEUE
from api.lib.decorator import flush_db
from api.lib.decorator import reconnect_db
from api.lib.perm.acl.cache import UserCache
from api.models.ansible import AnsibleExecution
from api.models.ansible import AnsibleExecutionDetail


def _ensure_user_context(uid):
    if not has_request_context():
        current_app.test_request_context().push()
    login_user(UserCache.get(uid) or UserCache.get('worker'))


@celery.task(name="cmdb.ansible_setup", queue=CMDB_QUEUE)
@flush_db
@reconnect_db
def ansible_setup(execution_id, ci_id, playbook, new_password, extra_params, uid):
    _ensure_user_context(uid)

    execution = AnsibleExecution.get_by_id(execution_id)
    if execution is None:
        current_app.logger.error('ansible_setup: execution %s not found', execution_id)
        return

    try:
        result = AnsibleSync().setup_server(
            ci_id,
            playbook=playbook or None,
            new_password=new_password or None,
            extra_params=extra_params or None,
        )

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
    except Exception as e:
        current_app.logger.exception('ansible_setup failed: execution_id=%s ci_id=%s', execution_id, ci_id)
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


@celery.task(name="cmdb.ansible_batch_setup", queue=CMDB_QUEUE)
@flush_db
@reconnect_db
def ansible_batch_setup(execution_id, ci_ids, playbook, new_password, extra_params, uid):
    _ensure_user_context(uid)

    execution = AnsibleExecution.get_by_id(execution_id)
    if execution is None:
        current_app.logger.error('ansible_batch_setup: execution %s not found', execution_id)
        return

    try:
        batch_result = AnsibleSync().setup_servers_batch(
            ci_ids,
            playbook=playbook or None,
            new_password=new_password or None,
            extra_params=extra_params or None,
        )

        exec_status = batch_result.get('status', 'Failed')
        hosts_result = batch_result.get('hosts_result', [])
        errors = batch_result.get('errors', [])
        success_count = sum(1 for h in hosts_result if h.get('status') == 'Success')
        failed_count = len(errors) + (len(hosts_result) - success_count)

        execution.update(
            status=exec_status,
            success_count=success_count,
            failed_count=failed_count,
        )

        for h in hosts_result:
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

        for err in errors:
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
    except Exception as e:
        current_app.logger.exception('ansible_batch_setup failed: execution_id=%s ci_ids=%s', execution_id, ci_ids)
        execution.update(status='Failed', success_count=0, failed_count=len(ci_ids) if ci_ids else 0)
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