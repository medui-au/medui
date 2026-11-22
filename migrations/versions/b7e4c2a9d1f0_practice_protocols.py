"""Practice protocols (ADR-171)

New tables only: protocol_measures, protocol_versions, protocol_options,
protocol_option_citations, protocol_modules, protocol_prevention_rules. No existing table,
prompt or pipeline is changed.

Revision ID: b7e4c2a9d1f0
Revises: c5d2f8a41e07
Create Date: 2026-11-22 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e4c2a9d1f0'
down_revision = 'c5d2f8a41e07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('protocol_measures',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=100), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=True),
    sa.Column('token_key', sa.String(length=40), nullable=True),
    sa.Column('scope', sa.Enum('protocol', 'individual', name='measurescope'), nullable=False),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('protocol_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'approved', 'retired', name='protocolstatus'), nullable=False),
    sa.Column('change_note', sa.Text(), nullable=True),
    sa.Column('copied_from_id', sa.Integer(), nullable=True),
    sa.Column('approved_by_id', sa.Integer(), nullable=True),
    sa.Column('approved_at', sa.DateTime(), nullable=True),
    sa.Column('review_due_on', sa.Date(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['copied_from_id'], ['protocol_versions.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('protocol_options',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('measure_id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=200), nullable=False),
    sa.Column('plan_wording', sa.Text(), nullable=True),
    sa.Column('patient_group', sa.String(length=300), nullable=True),
    sa.Column('default_rule', sa.JSON(), nullable=True),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('gp_sets', sa.Boolean(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['measure_id'], ['protocol_measures.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['protocol_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version_id', 'code', name='uq_protocol_option_code')
    )
    op.create_index(op.f('ix_protocol_options_version_id'), 'protocol_options', ['version_id'], unique=False)
    op.create_table('protocol_option_citations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('option_id', sa.Integer(), nullable=False),
    sa.Column('guideline_id', sa.Integer(), nullable=False),
    sa.Column('section_ref', sa.String(length=200), nullable=True),
    sa.Column('quote', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['guideline_id'], ['careplan_guidelines.id'], ),
    sa.ForeignKeyConstraint(['option_id'], ['protocol_options.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_protocol_option_citations_option_id'), 'protocol_option_citations', ['option_id'],
                    unique=False)
    op.create_table('protocol_modules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('condition_key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=150), nullable=False),
    sa.Column('applies_when', sa.JSON(), nullable=True),
    sa.Column('goals', sa.Text(), nullable=True),
    sa.Column('measures_text', sa.Text(), nullable=True),
    sa.Column('monitoring', sa.Text(), nullable=True),
    sa.Column('services', sa.JSON(), nullable=True),
    sa.Column('patient_info', sa.Text(), nullable=True),
    sa.Column('safety_netting', sa.Text(), nullable=True),
    sa.Column('gp_reference', sa.Text(), nullable=True),
    sa.Column('source_note', sa.Text(), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['version_id'], ['protocol_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version_id', 'condition_key', name='uq_protocol_module_key')
    )
    op.create_index(op.f('ix_protocol_modules_version_id'), 'protocol_modules', ['version_id'], unique=False)
    op.create_table('protocol_prevention_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=150), nullable=False),
    sa.Column('rule', sa.JSON(), nullable=False),
    sa.Column('wording', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['version_id'], ['protocol_versions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version_id', 'key', name='uq_protocol_prevention_key')
    )
    op.create_index(op.f('ix_protocol_prevention_rules_version_id'), 'protocol_prevention_rules', ['version_id'],
                    unique=False)


def downgrade():
    op.drop_index(op.f('ix_protocol_prevention_rules_version_id'), table_name='protocol_prevention_rules')
    op.drop_table('protocol_prevention_rules')
    op.drop_index(op.f('ix_protocol_modules_version_id'), table_name='protocol_modules')
    op.drop_table('protocol_modules')
    op.drop_index(op.f('ix_protocol_option_citations_option_id'), table_name='protocol_option_citations')
    op.drop_table('protocol_option_citations')
    op.drop_index(op.f('ix_protocol_options_version_id'), table_name='protocol_options')
    op.drop_table('protocol_options')
    op.drop_table('protocol_versions')
    op.drop_table('protocol_measures')
    sa.Enum(name='protocolstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='measurescope').drop(op.get_bind(), checkfirst=True)
