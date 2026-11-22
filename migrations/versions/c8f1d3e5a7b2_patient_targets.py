"""Patient targets (ADR-172)

A new table, patient_targets. Also links two seeded protocol measures to the care-plan
result tokens the app actually uses (ldl → ldl_c, hba1c → hba1c_ngsp), only where they still
carry the old seed values. No other table, prompt or pipeline is changed.

Revision ID: c8f1d3e5a7b2
Revises: b7e4c2a9d1f0
Create Date: 2026-11-22 10:00:00
"""
from alembic import op
import sqlalchemy as sa
import app.utils.encrypted_type


revision = 'c8f1d3e5a7b2'
down_revision = 'b7e4c2a9d1f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('patient_targets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('patient_id', sa.Integer(), nullable=False),
    sa.Column('measure_id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=True),
    sa.Column('value_text', sa.String(length=300), nullable=False),
    sa.Column('basis', sa.Enum('default', 'option', 'individual', name='targetbasis'), nullable=False),
    sa.Column('reason', app.utils.encrypted_type.EncryptedText(), nullable=True),
    sa.Column('set_by_id', sa.Integer(), nullable=False),
    sa.Column('set_at', sa.DateTime(), nullable=False),
    sa.Column('protocol_version_id', sa.Integer(), nullable=True),
    sa.Column('context', sa.String(length=20), nullable=False),
    sa.Column('superseded_at', sa.DateTime(), nullable=True),
    sa.Column('superseded_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['measure_id'], ['protocol_measures.id'], ),
    sa.ForeignKeyConstraint(['option_id'], ['protocol_options.id'], ),
    sa.ForeignKeyConstraint(['protocol_version_id'], ['protocol_versions.id'], ),
    sa.ForeignKeyConstraint(['set_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['superseded_by_id'], ['patient_targets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_patient_targets_patient_id'), 'patient_targets', ['patient_id'], unique=False)
    op.create_index('ix_patient_targets_current', 'patient_targets', ['patient_id', 'measure_id', 'superseded_at'],
                    unique=False)
    op.execute("UPDATE protocol_measures SET token_key = 'ldl_c' WHERE key = 'ldl' AND token_key = 'ldl'")
    op.execute("UPDATE protocol_measures SET token_key = 'hba1c_ngsp' WHERE key = 'hba1c' AND token_key = 'hba1c'")


def downgrade():
    op.drop_index('ix_patient_targets_current', table_name='patient_targets')
    op.drop_index(op.f('ix_patient_targets_patient_id'), table_name='patient_targets')
    op.drop_table('patient_targets')
    sa.Enum(name='targetbasis').drop(op.get_bind(), checkfirst=True)
