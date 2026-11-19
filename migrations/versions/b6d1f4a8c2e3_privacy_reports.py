"""privacy_reports: users report what got through to the AI (upstream ADR-115)

Revision ID: b6d1f4a8c2e3
Revises: f3a9c2d7b815
Create Date: 2026-10-25 16:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b6d1f4a8c2e3'
down_revision = 'f3a9c2d7b815'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'privacy_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('pipeline_runs.id'), nullable=False),
        sa.Column('reported_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reported_at', sa.DateTime(), nullable=False),
        sa.Column('span_start', sa.Integer(), nullable=False),
        sa.Column('span_end', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(200)),
        sa.Column('status', sa.String(16), nullable=False, server_default='open'),
        sa.Column('handled_by_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('handled_at', sa.DateTime()),
        sa.Column('outcome', sa.String(200)),
    )
    op.create_index('ix_privacy_reports_run_id', 'privacy_reports', ['run_id'])
    op.create_index('ix_privacy_reports_status', 'privacy_reports', ['status'])


def downgrade():
    op.drop_index('ix_privacy_reports_status', table_name='privacy_reports')
    op.drop_index('ix_privacy_reports_run_id', table_name='privacy_reports')
    op.drop_table('privacy_reports')
