from api.extensions import db
from api.lib.database import Model2


class AnsibleExecution(Model2):
    __tablename__ = "c_ansible_executions"

    uid = db.Column(db.Integer, index=True, nullable=False)
    playbook = db.Column(db.String(256), nullable=False)
    ci_ids = db.Column(db.JSON)
    ci_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='Running', index=True)
    extra_params = db.Column(db.JSON)


class AnsibleExecutionDetail(Model2):
    __tablename__ = "c_ansible_execution_details"

    execution_id = db.Column(db.Integer, db.ForeignKey("c_ansible_executions.id"), nullable=False, index=True)
    ci_id = db.Column(db.Integer, index=True, nullable=False)
    ci_name = db.Column(db.String(256))
    ip = db.Column(db.String(64))
    status = db.Column(db.String(20))
    returncode = db.Column(db.Integer)
    stdout = db.Column(db.Text)
    stderr = db.Column(db.Text)
