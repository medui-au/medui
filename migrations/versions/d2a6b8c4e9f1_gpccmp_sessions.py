"""GPCCMP sessions (ADR-173)

A new table only: gpccmp_sessions. No other table, prompt or pipeline is changed.

Revision ID: d2a6b8c4e9f1
Revises: c8f1d3e5a7b2
Create Date: 2026-11-22 12:00:00
"""
from alembic import op
import sqlalchemy as sa
import app.utils.encrypted_type


revision = 'd2a6b8c4e9f1'
down_revision = 'c8f1d3e5a7b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('gpccmp_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('plan_type', sa.String(length=10), nullable=False),
    sa.Column('status', sa.Enum('draft', 'ready', 'drafted', 'abandoned', name='sessionstatus'), nullable=False),
    sa.Column('decisions_json', app.utils.encrypted_type.EncryptedText(), nullable=True),
    sa.Column('protocol_version_id', sa.Integer(), nullable=True),
    sa.Column('pipeline_run_id', sa.Integer(), nullable=True),
    sa.Column('careplan_id', sa.Integer(), nullable=True),
    sa.Column('check_results', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['careplan_id'], ['careplans.id'], ),
    sa.ForeignKeyConstraint(['pipeline_run_id'], ['pipeline_runs.id'], ),
    sa.ForeignKeyConstraint(['protocol_version_id'], ['protocol_versions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gpccmp_sessions_patient_id'), 'gpccmp_sessions', ['patient_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_gpccmp_sessions_patient_id'), table_name='gpccmp_sessions')
    op.drop_table('gpccmp_sessions')
    sa.Enum(name='sessionstatus').drop(op.get_bind(), checkfirst=True)
