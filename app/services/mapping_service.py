"""MappingService — DDL + DML for admin-managed mapdata_* tables.

All table and column names are validated before interpolation into SQL.
Physical tables are always named mapdata_{name} and always have id SERIAL PRIMARY KEY.
"""

import csv
import io
import re
import math
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.models.mapping_table import MappingTable

_TABLE_RE = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
_COL_RE   = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
ALLOWED_TYPES = frozenset({'TEXT', 'INTEGER', 'BOOLEAN', 'NUMERIC', 'DATE', 'TIMESTAMP'})


def _q(identifier: str) -> str:
    """Double-quote a PostgreSQL identifier (already validated)."""
    return f'"{identifier}"'


def _validate_table(name: str) -> MappingTable:
    """Fetch registry row or raise ValueError."""
    if not _TABLE_RE.match(name):
        raise ValueError(f'Invalid table name: {name!r}')
    mt = MappingTable.query.filter_by(name=name).first()
    if not mt:
        raise ValueError(f'Unknown mapping table: {name!r}')
    return mt


def _validate_col(col: str) -> str:
    if not _COL_RE.match(col):
        raise ValueError(f'Invalid column name: {col!r}')
    return col


def _sanitize_col(raw: str) -> str:
    """Convert an arbitrary CSV header into a valid PostgreSQL column name.

    Replaces any character outside [a-z0-9_] with '_', collapses runs of
    underscores, strips leading/trailing underscores, and prefixes with 'x'
    if the result starts with a digit or is empty.
    """
    col = re.sub(r'[^a-z0-9_]', '_', raw.strip().lower())
    col = re.sub(r'_+', '_', col).strip('_')
    if not col:
        col = 'col'
    if col[0].isdigit():
        col = 'x' + col
    if len(col) > 63:
        col = col[:63]
    return col


# ── Registry ──────────────────────────────────────────────────────────────────

def list_tables() -> list[MappingTable]:
    return MappingTable.query.order_by(MappingTable.label).all()


def get_table(name: str) -> MappingTable | None:
    return MappingTable.query.filter_by(name=name).first()


def create_table(name: str, label: str, description: str = '') -> MappingTable:
    if not _TABLE_RE.match(name):
        raise ValueError(f'Invalid table name {name!r}. Use lowercase letters, digits, underscores (2–40 chars).')
    if MappingTable.query.filter_by(name=name).first():
        raise ValueError(f'A mapping table named {name!r} already exists.')
    phys = f'mapdata_{name}'
    db.session.execute(text(f'CREATE TABLE {_q(phys)} (id SERIAL PRIMARY KEY)'))
    mt = MappingTable(name=name, label=label or name, description=description or None)
    db.session.add(mt)
    db.session.commit()
    return mt


def drop_table(name: str) -> None:
    mt = _validate_table(name)
    db.session.execute(text(f'DROP TABLE IF EXISTS {_q(mt.physical_table)}'))
    db.session.delete(mt)
    db.session.commit()


def update_settings(name: str, label: str | None = None, description: str | None = None,
                    refresh_url: str | None = None, cache_ttl_seconds: int | None = None) -> MappingTable:
    mt = _validate_table(name)
    if label is not None:
        mt.label = label.strip() or mt.label
    if description is not None:
        mt.description = description.strip() or None
    if refresh_url is not None:
        mt.refresh_url = refresh_url.strip() or None
    if cache_ttl_seconds is not None:
        mt.cache_ttl_seconds = cache_ttl_seconds if cache_ttl_seconds > 0 else None
    mt.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return mt


# ── Physical table health ─────────────────────────────────────────────────────

def physical_table_exists(name: str) -> bool:
    """Return True if the physical mapdata_* table exists in the DB."""
    mt = _validate_table(name)
    return db.session.execute(text(
        "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='public' AND table_name=:t)"
    ), {'t': mt.physical_table}).scalar()


def recreate_physical_table(name: str) -> MappingTable:
    """Recreate a missing physical table. Preserves the registry entry and any prior columns."""
    mt = _validate_table(name)
    phys = f'mapdata_{name}'
    db.session.execute(text(f'CREATE TABLE IF NOT EXISTS {_q(phys)} (id SERIAL PRIMARY KEY)'))
    db.session.commit()
    return mt


# ── Schema inspection ─────────────────────────────────────────────────────────

def get_schema(name: str) -> list[dict]:
    """Return list of {column_name, data_type, is_nullable} dicts, excluding id."""
    mt = _validate_table(name)
    rows = db.session.execute(text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :tname
          AND column_name != 'id'
        ORDER BY ordinal_position
    """), {'tname': mt.physical_table}).mappings().all()
    return [dict(r) for r in rows]


# ── Data access ───────────────────────────────────────────────────────────────

def get_rows(name: str, page: int = 1, per_page: int = 50,
             sort_col: str | None = None, sort_dir: str = 'asc') -> tuple[list[dict], int]:
    """Return (rows, total_count) for pagination."""
    mt = _validate_table(name)
    phys = _q(mt.physical_table)

    # Validate sort column against actual schema
    schema_cols = {c['column_name'] for c in get_schema(name)} | {'id'}
    if sort_col and sort_col not in schema_cols:
        sort_col = None
    order_clause = f'{_q(sort_col)} {"DESC" if sort_dir == "desc" else "ASC"}' if sort_col else 'id ASC'

    total = db.session.execute(text(f'SELECT COUNT(*) FROM {phys}')).scalar()
    offset = (page - 1) * per_page
    rows = db.session.execute(
        text(f'SELECT * FROM {phys} ORDER BY {order_clause} LIMIT :lim OFFSET :off'),
        {'lim': per_page, 'off': offset}
    ).mappings().all()
    return [dict(r) for r in rows], total


def cell_update(name: str, row_id: int, col: str, value: str) -> None:
    mt = _validate_table(name)
    _validate_col(col)
    schema_cols = {c['column_name'] for c in get_schema(name)}
    if col not in schema_cols:
        raise ValueError(f'Column {col!r} not in table.')
    phys = _q(mt.physical_table)
    val = value if value != '' else None
    db.session.execute(
        text(f'UPDATE {phys} SET {_q(col)} = :val WHERE id = :rid'),
        {'val': val, 'rid': row_id}
    )
    db.session.commit()


def row_insert(name: str, data: dict) -> int:
    mt = _validate_table(name)
    schema_cols = {c['column_name'] for c in get_schema(name)}
    clean = {}
    for k, v in data.items():
        if k == 'id':
            continue
        _validate_col(k)
        if k in schema_cols:
            clean[k] = v if v != '' else None
    phys = _q(mt.physical_table)
    if not clean:
        row_id = db.session.execute(
            text(f'INSERT INTO {phys} DEFAULT VALUES RETURNING id')
        ).scalar()
    else:
        cols = ', '.join(_q(c) for c in clean)
        params = ', '.join(f':{c}' for c in clean)
        row_id = db.session.execute(
            text(f'INSERT INTO {phys} ({cols}) VALUES ({params}) RETURNING id'), clean
        ).scalar()
    db.session.commit()
    _sync_row_count(mt)
    return row_id


def row_delete(name: str, row_id: int) -> None:
    mt = _validate_table(name)
    phys = _q(mt.physical_table)
    db.session.execute(text(f'DELETE FROM {phys} WHERE id = :rid'), {'rid': row_id})
    db.session.commit()
    _sync_row_count(mt)


# ── Schema changes ────────────────────────────────────────────────────────────

def column_add(name: str, col_name: str, col_type: str) -> None:
    mt = _validate_table(name)
    _validate_col(col_name)
    col_type = col_type.upper()
    if col_type not in ALLOWED_TYPES:
        raise ValueError(f'Type {col_type!r} not allowed.')
    existing = {c['column_name'] for c in get_schema(name)}
    if col_name in existing or col_name == 'id':
        raise ValueError(f'Column {col_name!r} already exists.')
    phys = _q(mt.physical_table)
    db.session.execute(text(f'ALTER TABLE {phys} ADD COLUMN {_q(col_name)} {col_type}'))
    db.session.commit()


def column_retype(name: str, col_name: str, new_type: str) -> None:
    """Change an existing column's type. Raises ValueError if any value cannot be cast."""
    mt = _validate_table(name)
    _validate_col(col_name)
    new_type = new_type.upper()
    if new_type not in ALLOWED_TYPES:
        raise ValueError(f'Type {new_type!r} not allowed.')
    existing = {c['column_name'] for c in get_schema(name)}
    if col_name not in existing:
        raise ValueError(f'Column {col_name!r} does not exist.')
    phys = _q(mt.physical_table)
    try:
        db.session.execute(text(
            f'ALTER TABLE {phys} ALTER COLUMN {_q(col_name)} TYPE {new_type} '
            f'USING {_q(col_name)}::{new_type}'
        ))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        # Extract the useful part of the Postgres error (strip internal details)
        msg = str(exc.orig) if hasattr(exc, 'orig') else str(exc)
        raise ValueError(msg.split('\n')[0]) from exc


# ── Bulk operations ───────────────────────────────────────────────────────────

def csv_import(name: str, file_obj, replace: bool = True) -> dict:
    """Parse CSV, auto-add missing columns, insert rows. Returns {count, errors}."""
    mt = _validate_table(name)
    text_obj = io.TextIOWrapper(file_obj, encoding='utf-8-sig')
    reader = csv.DictReader(text_obj)
    if not reader.fieldnames:
        raise ValueError('CSV file has no header row.')

    # Normalise headers: sanitize to valid identifiers, skipping 'id'
    # col_map: sanitized_name -> original CSV header(s) for value lookup
    col_map: dict[str, str] = {}
    for raw in reader.fieldnames:
        orig = raw.strip()
        san  = _sanitize_col(orig)
        if san == 'id':
            continue
        if san not in col_map:
            col_map[san] = orig
    headers = list(col_map.keys())
    for h in headers:
        _validate_col(h)

    rows = list(reader)
    if not rows:
        return {'count': 0, 'errors': []}

    # Add missing columns
    existing_cols = {c['column_name'] for c in get_schema(name)}
    for h in headers:
        if h not in existing_cols:
            column_add(name, h, 'TEXT')

    phys = _q(mt.physical_table)
    if replace:
        db.session.execute(text(f'TRUNCATE TABLE {phys} RESTART IDENTITY'))

    errors = []
    count = 0
    cols_sql = ', '.join(_q(h) for h in headers)
    params_sql = ', '.join(f':{h}' for h in headers)
    insert_sql = text(f'INSERT INTO {phys} ({cols_sql}) VALUES ({params_sql})')
    for i, row in enumerate(rows, 1):
        try:
            params = {
                san: (row.get(orig) or row.get(orig.upper()) or '') or None
                for san, orig in col_map.items()
            }
            db.session.execute(insert_sql, params)
            count += 1
        except Exception as exc:
            errors.append(f'Row {i}: {exc}')
    db.session.commit()
    _sync_row_count(mt)
    return {'count': count, 'errors': errors}


def csv_export(name: str) -> str:
    """Return full table as CSV string."""
    mt = _validate_table(name)
    schema = get_schema(name)
    col_names = ['id'] + [c['column_name'] for c in schema]
    rows, _ = get_rows(name, page=1, per_page=999999)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=col_names, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def _api_refresh_csv(name: str, mt, raw_bytes: bytes) -> dict:
    """Handle a CSV response body for api_refresh — delegates to csv_import."""
    try:
        result = csv_import(name, io.BytesIO(raw_bytes), replace=True)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    now = datetime.now(timezone.utc)
    mt.last_refreshed_at = now
    db.session.commit()
    errs = result.get('errors', [])
    out: dict = {'ok': True, 'count': result['count'], 'refreshed_at': now.isoformat()}
    if errs:
        out['errors'] = errs
    return out


def api_refresh(name: str) -> dict:
    """GET the registered refresh_url and replace table contents. Returns {ok, count, error}."""
    import requests
    mt = _validate_table(name)
    if not mt.refresh_url:
        return {'ok': False, 'error': 'No refresh URL configured.'}
    try:
        resp = requests.get(mt.refresh_url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}

    # Route CSV responses (by content-type or when JSON parsing fails) through csv_import
    ct = resp.headers.get('Content-Type', '').lower()
    if 'csv' in ct or 'text/plain' in ct:
        return _api_refresh_csv(name, mt, resp.content)
    try:
        data = resp.json()
    except Exception:
        return _api_refresh_csv(name, mt, resp.content)

    # JSON path — accept list or dict with rows/data/results key
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get('rows') or data.get('data') or data.get('results') or []
    else:
        return {'ok': False, 'error': 'Unexpected response format.'}

    if not rows:
        now = datetime.now(timezone.utc)
        mt.last_refreshed_at = now
        db.session.commit()
        return {'ok': True, 'count': 0, 'refreshed_at': now.isoformat()}

    # Discover columns — sanitize keys so names like "date/time" are handled
    col_map: dict[str, str] = {}
    for row in rows:
        for k in row.keys():
            san = _sanitize_col(k)
            if san != 'id' and san not in col_map:
                col_map[san] = k

    existing_cols = {c['column_name'] for c in get_schema(name)}
    for san in col_map:
        if san not in existing_cols:
            column_add(name, san, 'TEXT')

    phys = _q(mt.physical_table)
    db.session.execute(text(f'TRUNCATE TABLE {phys} RESTART IDENTITY'))

    count = 0
    if col_map:
        cols_sql = ', '.join(_q(san) for san in col_map)
        params_sql = ', '.join(f':{san}' for san in col_map)
        insert_sql = text(f'INSERT INTO {phys} ({cols_sql}) VALUES ({params_sql})')
        for row in rows:
            norm = {san: row.get(orig) or row.get(orig.upper()) or None
                    for san, orig in col_map.items()}
            db.session.execute(insert_sql, norm)
            count += 1

    now = datetime.now(timezone.utc)
    mt.last_refreshed_at = now
    mt.row_count = count
    db.session.commit()
    return {'ok': True, 'count': count, 'refreshed_at': now.isoformat()}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_row_count(mt: MappingTable) -> None:
    phys = _q(mt.physical_table)
    count = db.session.execute(text(f'SELECT COUNT(*) FROM {phys}')).scalar()
    mt.row_count = count
    db.session.commit()


def page_range(current: int, total_pages: int, window: int = 3) -> list[int | None]:
    """Return page numbers with None as ellipsis markers."""
    if total_pages <= 1:
        return [1]
    pages: list[int | None] = []
    prev = None
    for p in range(1, total_pages + 1):
        if p == 1 or p == total_pages or abs(p - current) <= window:
            if prev is not None and p - prev > 1:
                pages.append(None)
            pages.append(p)
            prev = p
    return pages
