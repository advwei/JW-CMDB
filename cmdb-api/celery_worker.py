# -*- coding:utf-8 -*-

from api.app import create_app
from api.extensions import celery

# celery -A celery_worker.celery worker -l DEBUG -E -Q xxxx

app = create_app()
app.app_context().push()

# Unseal inner secrets in the celery worker process (gunicorn auto-unseals on
# startup, but celery does not), otherwise password decrypt fails with
# "secret is disabled, please seal firstly"
if app.config.get("SECRETS_ENGINE") == "inner":
    from api.extensions import inner_secrets
    from api.lib.secrets.secrets import InnerKVManger

    inner_secrets.backend = InnerKVManger()
    inner_secrets.trigger = app.config.get("INNER_TRIGGER_TOKEN")
    resp = inner_secrets.auto_unseal()
    inner_secrets.print_response(resp)

# Register ansible tasks
from api.tasks import ansible  # noqa: F401

# Load beat schedules from all modules
from api.tasks.cmdb import CMDB_BEAT_SCHEDULE

celery.conf.beat_schedule = celery.conf.get('beat_schedule', {})
celery.conf.beat_schedule.update(CMDB_BEAT_SCHEDULE)
