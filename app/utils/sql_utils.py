"""SQL utility functions for the Query Manager and PatientJSON block execution.

Named parameter convention
--------------------------
SQL in the Query Manager uses :name placeholders (SQL Server / PostgreSQL compatible
named style).  When executing against BPSDB (pyodbc/SQL Server) these must be
converted to positional ? placeholders — use named_to_positional() for that.
PostgreSQL executions can use named params directly via SQLAlchemy text().

System parameters are injected automatically; they must NOT appear as manual
input fields in the Query Manager UI.
"""

import re
from datetime import datetime

# Auto-injected at execution time — excluded from the UI param input fields.
SYSTEM_PARAMS: frozenset = frozenset({
    'current_patient_id',
    'current_user_id',
    'today',
    'current_year',
    'current_month',
    # Common legacy aliases automatically mapped to patient_id
    'vBPId',
    'InternalId',
    'patient_id',
})

# Known patient_id parameter aliases — tried in order when executing an
# app-enabled query from the PatientJSON / bundle context.
PATIENT_ID_ALIASES: tuple = (
    'current_patient_id',
    'vBPId',
    'InternalId',
    'patient_id',
)


def extract_sql_parameters(sql_text: str) -> list[str]:
    """Return user-supplied :name placeholders that require manual input.

    System parameters (SYSTEM_PARAMS) are excluded.
    Preserves first-occurrence order; no duplicates.
    """
    if not sql_text:
        return []
    found = re.findall(r'(?<!:):([a-zA-Z0-9_]+)', sql_text)
    seen: set = set()
    return [
        p for p in found
        if p not in SYSTEM_PARAMS and not (p in seen or seen.add(p))
    ]


def extract_system_params_used(sql_text: str) -> list[str]:
    """Return which SYSTEM_PARAMS are referenced in the SQL (for display only)."""
    if not sql_text:
        return []
    found = re.findall(r'(?<!:):([a-zA-Z0-9_]+)', sql_text)
    seen: set = set()
    return [
        p for p in found
        if p in SYSTEM_PARAMS and not (p in seen or seen.add(p))
    ]


def build_system_params(patient_id=None, user_id=None) -> dict:
    """Build the standard system parameter dict for query execution."""
    now = datetime.today()
    pid = int(patient_id) if patient_id else None
    return {
        'current_patient_id': pid,
        'vBPId':              pid,
        'InternalId':         pid,
        'patient_id':         pid,
        'current_user_id':    user_id,
        'today':              now.strftime('%Y-%m-%d'),
        'current_year':       now.strftime('%Y'),
        'current_month':      now.strftime('%m'),
    }


def named_to_positional(sql_text: str, params: dict) -> tuple[str, list]:
    """Convert :name placeholders to ? and return (sql, ordered_values).

    Used when executing named-param SQL against BPSDB (pyodbc requires ?).
    Unknown placeholders are replaced with NULL.
    """
    values: list = []

    def replace(match):
        name = match.group(1)
        values.append(params.get(name))
        return '?'

    converted = re.sub(r'(?<!:):([a-zA-Z0-9_]+)', replace, sql_text)
    return converted, values


def execute_sql_query(sql_query, patient_id: int | None = None,
                      user_id: int | None = None,
                      extra_params: dict | None = None) -> list[dict]:
    """Execute a SQLQuery model instance against the appropriate database.

    Merges system params, then extra_params (user-supplied from form).
    Returns a list of row dicts.  Raises on connection or query error.
    """
    from flask import current_app

    params = build_system_params(patient_id=patient_id, user_id=user_id)
    if extra_params:
        params.update(extra_params)

    if sql_query.database_target == 'postgres':
        from sqlalchemy import text
        from app.extensions import db
        result = db.session.execute(text(sql_query.sql_text), params)
        return [dict(row._mapping) for row in result]

    # BPSDB — SQL written in MedUI runs only through a login confirmed read-only (ADR-139)
    from app.services.bp_login_service import require_read_only
    require_read_only()
    # convert named → positional for pyodbc
    from app.sql.query_loader import ReadOnlySession
    sql, positional = named_to_positional(sql_query.sql_text, params)
    with ReadOnlySession(current_app.config['BPSDB_URI']) as session:
        return session.execute(sql, positional)
