"""add ansible execution history tables

Revision ID: c_ansible_exec
Revises: 6a4df2623057
Create Date: 2026-07-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c_ansible_exec'
down_revision = '6a4df2623057'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'c_ansible_executions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('uid', sa.Integer(), nullable=False),
        sa.Column('playbook', sa.String(256), nullable=False),
        sa.Column('ci_ids', sa.JSON(), nullable=True),
        sa.Column('ci_count', sa.Integer(), server_default='0'),
        sa.Column('success_count', sa.Integer(), server_default='0'),
        sa.Column('failed_count', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(20), server_default='Running'),
        sa.Column('extra_params', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_c_ansible_executions_created_at', 'c_ansible_executions', ['created_at'])
    op.create_index('ix_c_ansible_executions_uid', 'c_ansible_executions', ['uid'])
    op.create_index('ix_c_ansible_executions_status', 'c_ansible_executions', ['status'])

    op.create_table(
        'c_ansible_execution_details',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('execution_id', sa.Integer(), nullable=False),
        sa.Column('ci_id', sa.Integer(), nullable=False),
        sa.Column('ci_name', sa.String(256), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('status', sa.String(20), nullable=True),
        sa.Column('returncode', sa.Integer(), nullable=True),
        sa.Column('stdout', sa.Text(), nullable=True),
        sa.Column('stderr', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['execution_id'], ['c_ansible_executions.id']),
    )
    op.create_index('ix_c_ansible_execution_details_execution_id', 'c_ansible_execution_details', ['execution_id'])
    op.create_index('ix_c_ansible_execution_details_ci_id', 'c_ansible_execution_details', ['ci_id'])


def downgrade():
    op.drop_table('c_ansible_execution_details')
    op.drop_table('c_ansible_executions')
