"""Practice documents and their versions (ADR-184)

New tables only: practice_documents, practice_document_versions. No other table is changed. The
AI-use policy already saved in system_settings becomes version 1 the first time it is read.

Revision ID: e1f4a7c3b9d2
Revises: d2a6b8c4e9f1
Create Date: 2026-11-22 20:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = 'e1f4a7c3b9d2'
down_revision = 'd2a6b8c4e9f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('practice_documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('practice_document_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('markdown', sa.Text(), nullable=False),
    sa.Column('note', sa.String(length=300), nullable=True),
    sa.Column('snapshot', sa.JSON(), nullable=True),
    sa.Column('saved_by_id', sa.Integer(), nullable=True),
    sa.Column('saved_by_name', sa.String(length=120), nullable=True),
    sa.Column('saved_at', sa.DateTime(), nullable=False),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_name', sa.String(length=120), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('review_due_on', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['practice_documents.id'], ),
    sa.ForeignKeyConstraint(['saved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'number', name='uq_practice_document_version')
    )
    op.create_index(op.f('ix_practice_document_versions_document_id'), 'practice_document_versions',
                    ['document_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_practice_document_versions_document_id'), table_name='practice_document_versions')
    op.drop_table('practice_document_versions')
    op.drop_table('practice_documents')
