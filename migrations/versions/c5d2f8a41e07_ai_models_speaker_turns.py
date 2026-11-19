"""ai_models.speaker_turns: Deepgram speaker separation per ASR model (ADR-151)

NULL (the default, and every existing model) is off: transcription and the local labelling
step work as before.

Revision ID: c5d2f8a41e07
Revises: a7c3e9d1b246
Create Date: 2026-11-15 19:30:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d2f8a41e07'
down_revision = 'a7c3e9d1b246'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('ai_models', sa.Column('speaker_turns', sa.String(length=10), nullable=True))


def downgrade():
    op.drop_column('ai_models', 'speaker_turns')
