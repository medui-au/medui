"""privacy_reviews: an administrator's verdict on a run's privacy-check hits (upstream ADR-120)

The Privacy Review page starts switched off (no privacy.review_page row): an administrator
turns it on in Application Setup → Maintenance.

Revision ID: d7f3b9e1a5c4
Revises: c4e8a2d6f1b9
Create Date: 2026-10-30 20:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd7f3b9e1a5c4'
down_revision = 'c4e8a2d6f1b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'privacy_reviews',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('pipeline_runs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('disposition', sa.String(20), nullable=False),
        sa.Column('severity', sa.String(10)),
        sa.Column('comment', sa.Text()),
        sa.Column('reviewed_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_privacy_reviews_run_id', 'privacy_reviews', ['run_id'], unique=True)


def downgrade():
    op.drop_index('ix_privacy_reviews_run_id', table_name='privacy_reviews')
    op.drop_table('privacy_reviews')
