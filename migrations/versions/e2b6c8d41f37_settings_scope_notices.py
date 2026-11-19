"""My settings, AI scope and notices (upstream ADR-085, ADR-087, ADR-088)

user_preferences: personal settings per user; the scribe's per-user
SystemSetting keys are copied in (they stay, as upstream).
scope_wordings + system_prompts.scope_key: the four scope instructions and the
five on-screen notices, editable in Setup → AI scope. Which scope each seeded
system prompt uses comes with the seed data (and the seed resync fills it for
existing installs); NULL means the practice default.

Revision ID: e2b6c8d41f37
Revises: d4e7a1c90b21
Create Date: 2026-10-21 19:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2b6c8d41f37'
down_revision = 'd4e7a1c90b21'
branch_labels = None
depends_on = None

_SCRIBE_KEYS = ('scribe.asr_model', 'scribe.pipeline', 'scribe.chunk_interval_ms')

_WORDINGS = [
    ('instruction', 'record', 'Record — organise and summarise what the record says',
     "Your role is to list, organise, summarise and extract what the material provided says. "
     "You may restate a diagnosis, medicine, dose, result or plan only as it is written in the "
     "material, and say where it comes from. Do not add, infer or recommend any diagnosis, "
     "treatment, medicine, dose, prognosis or management that the material does not state."),
    ('instruction', 'scribe', 'Scribe — write up only what was said',
     "Your role is to write up what was said in the consultation, for the clinician to review. "
     "Include only what was said or discussed. Do not add any diagnosis, differential diagnosis, "
     "treatment, medicine, dose, prognosis or plan that was not stated or discussed."),
    ('instruction', 'correspondence', 'Correspondence — draft from the facts supplied',
     "Your role is to draft correspondence from the facts the clinician has supplied. "
     "Keep to those facts. Do not add clinical advice, diagnoses, treatments or doses beyond "
     "what the clinician wrote or the material states."),
    ('instruction', 'general', 'General — reference and administrative help',
     "Your role is general reference and administrative help for a medical practice. "
     "Do not give a diagnosis, treatment, medicine, dose or prognosis for a particular patient, "
     "and do not act as a second opinion on a patient's care."),
    ('notice', 'draft', 'AI draft — check before use',
     'AI draft — check it against the record before you file, send or act on it. '
     'You remain responsible for what you use.'),
    ('notice', 'chat_patient', "Patient chat — drafted from this patient's record",
     'Answers are drafted by AI from this patient’s record — check them against the '
     'record before relying on them.'),
    ('notice', 'chat_general', 'General chat — drafted from general knowledge',
     'Answers are drafted by AI from general knowledge, not from a patient’s record — '
     'check them before relying on them.'),
    ('notice', 'summary', 'Summary — what the record says, not an interpretation',
     'AI summary of what the record says, not an interpretation of it — check it against '
     'the record before relying on it.'),
    ('notice', 'scribe', 'Scribe — written from what was said',
     'Written by AI from what was said in the consultation — check it before you file it. '
     'You remain responsible for the note.'),
]


def upgrade():
    op.create_table('user_preferences',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=120), nullable=False),
    sa.Column('value_json', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'key', name='uq_user_preferences_user_key')
    )
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_preferences_user_id'), ['user_id'], unique=False)

    op.create_table('scope_wordings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('kind', 'key', 'version', name='uq_scope_wordings_kind_key_version')
    )
    with op.batch_alter_table('system_prompts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('scope_key', sa.String(length=40), nullable=True))

    conn = op.get_bind()
    for base in _SCRIBE_KEYS:
        conn.execute(sa.text(
            """
            INSERT INTO user_preferences (user_id, key, value_json, updated_at)
            SELECT u.id, :base, s.value_json, now()
              FROM system_settings s
              JOIN users u ON s.key = :base || '.' || u.id::text
            """
        ), {'base': base})
    for kind, key, label, text in _WORDINGS:
        conn.execute(sa.text(
            "INSERT INTO scope_wordings (kind, key, label, text, version, is_active, created_at) "
            "VALUES (:kind, :key, :label, :text, 1, true, now())"
        ), {'kind': kind, 'key': key, 'label': label, 'text': text})


def downgrade():
    with op.batch_alter_table('system_prompts', schema=None) as batch_op:
        batch_op.drop_column('scope_key')
    op.drop_table('scope_wordings')
    with op.batch_alter_table('user_preferences', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_preferences_user_id'))
    op.drop_table('user_preferences')
