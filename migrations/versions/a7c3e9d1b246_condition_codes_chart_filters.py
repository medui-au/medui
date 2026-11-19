"""condition_codes: the population chart's three filter conditions (ADR-146)

Adds osa, wboa and depression_anxiety, with the codes the chart always used, to an existing
condition_codes table. A condition that already has rows is left as it is. A new install
gets them from condition_codes.DEFAULTS when the table is first made.

Revision ID: a7c3e9d1b246
Revises: 758aa1d84d18
Create Date: 2026-11-14 09:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c3e9d1b246'
down_revision = '758aa1d84d18'
branch_labels = None
depends_on = None

ADDED = {
    'osa': ((3347, 8070, 8071), 'Sleep apnoea: population chart filter'),
    'wboa': ((3718, 3719, 3793, 2577, 2576, 2573),
             'Osteoarthritis of weight-bearing joints: population chart filter'),
    'depression_anxiety': ((243, 2029, 758, 760, 757, 5205, 2233, 27517, 7920, 5893),
                           'Depression or anxiety: population chart filter'),
}


def upgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT to_regclass('public.mapdata_condition_codes')")).scalar() is None:
        return   # no table yet: it is made with every default on first use
    for condition, (codes, note) in ADDED.items():
        present = bind.execute(sa.text(
            'SELECT 1 FROM mapdata_condition_codes WHERE "condition" = :c LIMIT 1'), {'c': condition}).first()
        if present:
            continue
        for code in codes:
            bind.execute(sa.text(
                'INSERT INTO mapdata_condition_codes ("condition", item_code, note) VALUES (:c, :i, :n)'),
                {'c': condition, 'i': code, 'n': note})


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT to_regclass('public.mapdata_condition_codes')")).scalar() is None:
        return
    for condition, (_codes, note) in ADDED.items():
        bind.execute(sa.text(
            'DELETE FROM mapdata_condition_codes WHERE "condition" = :c AND note = :n'),
            {'c': condition, 'n': note})
