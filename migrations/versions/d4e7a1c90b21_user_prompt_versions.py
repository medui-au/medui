"""User prompt versions: earlier text kept when the seed resync replaces a prompt

Revision ID: d4e7a1c90b21
Revises: c29f5153a007
Create Date: 2026-10-21 17:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e7a1c90b21'
down_revision = 'c29f5153a007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('user_prompt_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_prompt_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('prompt_text', sa.Text(), nullable=False),
    sa.Column('system_prompt_name', sa.String(length=200), nullable=True),
    sa.Column('classifier', sa.String(length=80), nullable=True),
    sa.Column('temperature', sa.Float(), nullable=True),
    sa.Column('max_tokens', sa.Integer(), nullable=True),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.Column('saved_at', sa.DateTime(), nullable=True),
    sa.Column('saved_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['saved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_prompt_id'], ['user_prompts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_prompt_id', 'version')
    )
    with op.batch_alter_table('user_prompt_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_prompt_versions_user_prompt_id'), ['user_prompt_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_prompt_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_prompt_versions_user_prompt_id'))
    op.drop_table('user_prompt_versions')
