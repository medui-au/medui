"""Condition names for the condition_codes table from two independent sources (ADR-183).
Invented names and counts only. Database tests need MEDUI_TEST_DATABASE_URL (a *_test database)."""
import pytest

from app.services import condition_codes as cc
from tests.test_practice_protocols import ctx, needs_db  # noqa: F401  (ctx is a fixture)


def test_bp_names_join_synonyms_and_mark_retired_terms():
    terms = [{'TERMID': 9001, 'TERMNAME': 'Invented condition', 'RECORDSTATUS': 1},
             {'TERMID': 9001, 'TERMNAME': 'Invented condition, synonym', 'RECORDSTATUS': 1},
             {'TERMID': 9001, 'TERMNAME': 'Old invented name', 'RECORDSTATUS': 0},
             {'TERMID': 9002, 'TERMNAME': 'Retired invented term', 'RECORDSTATUS': 0}]
    names = cc.bp_names(terms)
    assert names[9001] == 'Invented condition / Invented condition, synonym'
    assert names[9002] == 'Retired invented term (no longer current in BP)'


def test_practice_names_take_the_most_used_text_and_never_a_rare_one():
    texts = [{'ITEMCODE': 9001, 'ITEMTEXT': 'Invented condition', 'N': 40},
             {'ITEMCODE': 9001, 'ITEMTEXT': 'Invented cond.', 'N': 12},
             {'ITEMCODE': 9002, 'ITEMTEXT': 'Wording used twice', 'N': 2},
             {'ITEMCODE': 9003, 'ITEMTEXT': '  ', 'N': 9},
             {'ITEMCODE': None, 'ITEMTEXT': 'No code', 'N': 9}]
    names = cc.practice_names(texts)
    assert names == {9001: 'Invented condition'}


def test_the_practice_query_returns_no_patient_columns_or_rare_texts():
    sql = open('app/sql/condition_item_texts.sql').read().upper()
    body = sql.split('SELECT', 1)[1]
    assert 'HAVING COUNT(*) >= 3' in body
    for col in ('INTERNALID', 'PATIENTID', 'RECORDID', 'FIRSTNAME', 'SURNAME', 'DOB'):
        assert col not in body
    assert 'BPSDRUGS' not in sql


@needs_db
def test_each_column_fills_on_its_own(ctx, monkeypatch):
    from sqlalchemy import text
    from app.services import mapping_service as ms
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()
    cc.ensure_table()
    code = cc.DEFAULTS['diabetes'][0][0]
    ctx.app.config['BPSDB_URI'] = 'invented://bp'

    def fake_read(available):
        def read(query):
            if query not in available:
                return None                      # as when the login can't read that database
            if query == 'condition_term_names':
                return [{'TERMID': code, 'TERMNAME': 'Invented dictionary name', 'RECORDSTATUS': 1}]
            return [{'ITEMCODE': code, 'ITEMTEXT': 'Invented practice wording', 'N': 5}]
        return read

    def cells():
        rows, _ = ms.get_rows(cc.TABLE, page=1, per_page=10000)
        r = next(r for r in rows if r['item_code'] == code)
        return r.get('bp_item'), r.get('practice_item'), rows

    # No BPSDrugs access: practice_item fills, bp_item stays blank.
    monkeypatch.setattr(cc, '_read_bp', fake_read({'condition_item_texts'}))
    monkeypatch.setattr(cc, '_names_filled', False)
    cc._fill_names(cells()[2])
    bp, practice, _ = cells()
    assert not bp and practice == 'Invented practice wording'

    # Next start, with access: bp_item fills; practice_item is kept as it was.
    monkeypatch.setattr(cc, '_read_bp', fake_read({'condition_term_names', 'condition_item_texts'}))
    monkeypatch.setattr(cc, '_names_filled', False)
    cc._fill_names(cells()[2])
    bp, practice, _ = cells()
    assert bp == 'Invented dictionary name' and practice == 'Invented practice wording'

    # Neither source: nothing changes and nothing fails.
    monkeypatch.setattr(cc, '_read_bp', fake_read(set()))
    monkeypatch.setattr(cc, '_names_filled', False)
    cc._fill_names(cells()[2])
    assert cells()[:2] == (bp, practice)
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()


@needs_db
def test_an_older_table_gets_the_new_column(ctx, monkeypatch):
    from sqlalchemy import text
    from app.services import mapping_service as ms
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()
    cc.ensure_table()
    ctx.db.session.execute(text('ALTER TABLE mapdata_condition_codes DROP COLUMN practice_item'))
    ctx.db.session.commit()
    monkeypatch.setattr(cc, '_columns_checked', False)
    assert cc.ensure_table() is False
    assert 'practice_item' in {c['column_name'] for c in ms.get_schema(cc.TABLE)}
    assert 'practice_item' in ms.get_table(cc.TABLE).description
    ctx.db.session.execute(text('DROP TABLE IF EXISTS mapdata_condition_codes'))
    ctx.db.session.commit()
