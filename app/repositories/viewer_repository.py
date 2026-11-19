from app.services import practitioner_names
import re
import pyodbc
from contextlib import contextmanager

from flask import current_app
from app.sql.query_loader import ReadOnlySession, load_query


class ViewerRepository:
    def __init__(self, session: ReadOnlySession):
        self._session = session

    # ── Metadata queries (main BPSDB) ─────────────────────────────────────────

    def get_letter_meta(self, record_id: int) -> dict | None:
        rows = self._session.execute(load_query('viewer_letter_meta'), [record_id])
        return rows[0] if rows else None

    def get_path_filed(self, report_id: int) -> dict | None:
        rows = practitioner_names.swap(self._session.execute(load_query('viewer_path_filed'), [report_id]),
                                       'DOCTOR_USERID', 'DOCTOR_NAME')
        return rows[0] if rows else None

    def get_path_inbox(self, report_id: int) -> dict | None:
        rows = practitioner_names.swap(self._session.execute(load_query('viewer_path_inbox'), [report_id]),
                                       'DOCTOR_USERID', 'DOCTOR_NAME')
        return rows[0] if rows else None

    def get_scan_meta(self, document_id: int) -> dict | None:
        rows = self._session.execute(load_query('viewer_scan_meta'), [document_id])
        return rows[0] if rows else None

    # ── Binary content (BPSDocuments{N} dynamic databases) ────────────────────

    @contextmanager
    def _dynamic_conn(self, stored: int):
        """Open a connection to BPSDocuments{stored}, yield it, then close.
        Yields None gracefully if the connection fails."""
        uri = current_app.config.get('BPSDB_URI', '')
        if not uri:
            current_app.logger.error('viewer: BPSDB_URI not configured')
            yield None
            return

        db_name = f'BPSDocuments{stored}'
        new_uri = re.sub(r'(?i)DATABASE=[^;]+', f'DATABASE={db_name}', uri)
        if new_uri == uri:
            new_uri = uri.rstrip(';') + f';DATABASE={db_name}'

        conn = None
        try:
            conn = pyodbc.connect(new_uri, autocommit=True)
            yield conn
        except pyodbc.Error as exc:
            current_app.logger.error('viewer: cannot connect to %s — %s', db_name, exc)
            yield None
        finally:
            if conn:
                conn.close()

    def get_letter_binary(self, record_id: int, stored: int) -> bytes | None:
        with self._dynamic_conn(stored) as conn:
            if conn is None:
                return None
            try:
                row = conn.cursor().execute(
                    'SELECT CONTENT FROM dbo.LETTERS WHERE ITEMID = ?', [record_id]
                ).fetchone()
                return bytes(row[0]) if row else None
            except pyodbc.Error as exc:
                current_app.logger.error('get_letter_binary(%d, %d): %s', record_id, stored, exc)
                return None

    def get_path_binary(self, page_id: int, stored: int) -> bytes | None:
        with self._dynamic_conn(stored) as conn:
            if conn is None:
                return None
            try:
                row = conn.cursor().execute(
                    'SELECT CONTENT FROM dbo.INVESTIGATIONS WHERE INVESTIGATIONPAGEID = ?', [page_id]
                ).fetchone()
                return bytes(row[0]) if row else None
            except pyodbc.Error as exc:
                current_app.logger.error('get_path_binary(%d, %d): %s', page_id, stored, exc)
                return None

    def get_scan_binary(self, page_id: int, stored: int) -> tuple[bytes, str, int] | None:
        with self._dynamic_conn(stored) as conn:
            if conn is None:
                return None
            try:
                row = conn.cursor().execute(
                    'SELECT content, DocType, Compression FROM dbo.DOCUMENTS WHERE DocumentPageId = ?',
                    [page_id]
                ).fetchone()
                if row:
                    return (bytes(row[0]), (row[1] or '').strip().upper(), row[2] or 0)
                return None
            except pyodbc.Error as exc:
                current_app.logger.error('get_scan_binary(%d, %d): %s', page_id, stored, exc)
                return None
