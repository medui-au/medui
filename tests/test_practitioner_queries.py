"""Practitioner queries keep inactive and deleted users (upstream ADR-112).

A practice can enter a "shadow" BP user under a practitioner's preferred name so that
tools reading only BP redact and detect it. That works only while these queries have
no status filter; this test fails if one is added. The redaction and checker queries are
the bps_redaction core's since ADR-114, guarded by the same test there; MedUI keeps this one.
"""
import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[1] / "app/sql"
FILES = ('staff_users.sql',)


def _code(path):
    return "\n".join(l.split("--")[0] for l in path.read_text().splitlines())


def test_no_status_filter_on_practitioner_queries():
    for name in FILES:
        code = _code(SQL_DIR / name)
        assert not re.search(r"\b(USERSTATUS|RECORDSTATUS)\b", code, re.I), name

