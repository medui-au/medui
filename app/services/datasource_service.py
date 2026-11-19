"""General-purpose fetch dispatcher for DataSource records.

Returns a normalised result dict:
  { 'columns': [...], 'rows': [dict, ...], 'row_count': int, 'error': str|None }

Dispatch is based on DataSource.location_type:
  http_url     — fetch a CSV via HTTP
  local_file   — read a local CSV path
  network_path — read a UNC/mounted network CSV path (same as local_file in Python)
  bpsdb_query  — execute a named SQLQuery via ReadOnlySession
"""
import csv
import io
from typing import Any

import requests

from app.models.data_source import (
    LOCATION_HTTP, LOCATION_LOCAL, LOCATION_NETWORK, LOCATION_BPSDB,
)

_TIMEOUT = 10
_EMPTY   = {'columns': [], 'rows': [], 'row_count': 0, 'error': None}


def fetch(source) -> dict[str, Any]:
    """Fetch and normalise data from a DataSource model instance."""
    try:
        lt = source.location_type
        if lt == LOCATION_HTTP:
            return _from_http(source.location)
        if lt in (LOCATION_LOCAL, LOCATION_NETWORK):
            return _from_file(source.location)
        if lt == LOCATION_BPSDB:
            return _from_bpsdb(source.location)
        return {**_EMPTY, 'error': f'Unknown location_type: {lt}'}
    except Exception as exc:
        return {**_EMPTY, 'error': str(exc)}


def rows_to_csv_text(result: dict[str, Any]) -> str:
    """Convert a fetch() result dict to a CSV string (for AI input)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=result['columns'])
    writer.writeheader()
    writer.writerows(result['rows'])
    return buf.getvalue()


# ── Fetchers ──────────────────────────────────────────────────────────────────

def _from_http(url: str) -> dict[str, Any]:
    resp = requests.get(url, timeout=_TIMEOUT)
    resp.raise_for_status()
    return _parse_csv(resp.content.decode('utf-8-sig'))


def _from_file(path: str) -> dict[str, Any]:
    with open(path, newline='', encoding='utf-8-sig') as fh:
        return _parse_csv(fh.read())


def _from_bpsdb(query_name: str) -> dict[str, Any]:
    from app.models.sql_query import SQLQuery
    from app.utils.sql_utils import execute_sql_query, build_system_params
    sq = SQLQuery.query.filter_by(name=query_name).first()
    if not sq:
        return {**_EMPTY, 'error': f'SQLQuery "{query_name}" not found.'}
    if not sq.is_app_enabled:
        return {**_EMPTY, 'error': f'SQLQuery "{query_name}" is not app-enabled.'}
    rows = execute_sql_query(sq)
    if not rows:
        return _EMPTY
    columns = list(rows[0].keys())
    # Enforce row limit from SQLQuery config
    if sq.app_row_limit and len(rows) > sq.app_row_limit:
        rows = rows[:sq.app_row_limit]
    return {'columns': columns, 'rows': rows, 'row_count': len(rows), 'error': None}


def _parse_csv(text: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(text))
    rows   = list(reader)
    if not rows:
        return _EMPTY
    columns = list(rows[0].keys())
    # Cast numeric strings to float where possible
    cast_rows = []
    for r in rows:
        cast_rows.append({
            k: _maybe_float(v) for k, v in r.items()
        })
    return {'columns': columns, 'rows': cast_rows, 'row_count': len(cast_rows), 'error': None}


def _maybe_float(v: str):
    try:
        return float(v)
    except (TypeError, ValueError):
        return v
