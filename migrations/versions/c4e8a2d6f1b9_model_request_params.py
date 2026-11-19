"""ai_models: request_params, extra request parameters per model (upstream ADR-119)

Revision ID: c4e8a2d6f1b9
Revises: b6d1f4a8c2e3
Create Date: 2026-10-30 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4e8a2d6f1b9'
down_revision = 'b6d1f4a8c2e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ai_models', schema=None) as batch_op:
        batch_op.add_column(sa.Column('request_params', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('ai_models', schema=None) as batch_op:
        batch_op.drop_column('request_params')
