"""users: preferred_name and bp_display_name (upstream ADR-106)

Revision ID: f3a9c2d7b815
Revises: e2b6c8d41f37
Create Date: 2026-10-24

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a9c2d7b815'
down_revision = 'e2b6c8d41f37'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('preferred_name', sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('bp_display_name', sa.String(120), nullable=True))
    # Until each user's next login, the BP name is the name MedUI already holds.
    op.execute('UPDATE users SET bp_display_name = display_name')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('bp_display_name')
        batch_op.drop_column('preferred_name')
