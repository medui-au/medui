"""document_service — format dispatch for binary clinical documents.

Takes raw bytes + metadata and returns a DocumentResult describing how to
render the content.  All format detection and conversion lives here so that
blueprint routes stay thin.

Supported formats
-----------------
RTF           → plain text extracted via striprtf, wrapped in pre-formatted HTML
PDF           → pass-through bytes (browser displays natively in an iframe)
TIF/TIFF      → converted to PNG via Pillow for browser display
BMP/JPG/PNG   → pass-through bytes
HTML/HTM      → decoded UTF-8 string
CDA/XML       → XSLT transform to HTML via default.xsl (falls back to escaped XML)
ZIP           → first file extracted; type re-detected by extension
              (REPORTHEADER/REPORTBODY fields may also be zipped — handled in render_path_report)
Fallback      → attempt UTF-8 decode and display as pre-formatted text
"""

import io
import os
import re
import zlib
import html as html_lib
from typing import NamedTuple
from zipfile import ZipFile, BadZipFile

from flask import current_app, has_app_context

_XSL_PATH = os.path.join(os.path.dirname(__file__), 'text_processing', 'default.xsl')


# ── CDA helper ────────────────────────────────────────────────────────────────

def _cda_to_html(xml_data: bytes) -> str | None:
    """Transform CDA XML to HTML using default.xsl.  Returns None on failure."""
    try:
        from lxml import etree
        xsl_path = os.path.normpath(_XSL_PATH)
        xsl_doc  = etree.parse(xsl_path)
        transform = etree.XSLT(xsl_doc)
        xml_doc  = etree.fromstring(xml_data, etree.XMLParser(recover=True))
        return str(transform(xml_doc))
    except Exception as exc:
        current_app.logger.warning('CDA XSLT transform failed: %s', exc)
        return None


# ── Result type ───────────────────────────────────────────────────────────────

class DocumentResult(NamedTuple):
    render_type: str    # 'html' | 'pdf' | 'image'
    content: bytes | str
    mimetype: str
    # What OCR should read, when it isn't the displayed content: a multi-page
    # TIFF is shown as a first-page PNG, so OCR gets the original instead.
    ocr_source: bytes | None = None
    ocr_mime: str = ''


_HTML_UNAVAILABLE = DocumentResult(
    'html',
    '<p style="color:var(--text-muted);padding:1rem;">'
    'Document temporarily unavailable — database access error.</p>',
    'text/html; charset=utf-8',
)

_HTML_EMPTY = DocumentResult(
    'html',
    '<p style="color:var(--text-muted);padding:1rem;">No content available for this document.</p>',
    'text/html; charset=utf-8',
)

# A ZIP that opens but whose content can't be read: an unsupported method (Deflate64,
# zip method 9, found in BP's sample databases), encryption or damaged data.
_UNPACK_ERRORS = (NotImplementedError, RuntimeError, zlib.error, EOFError)
_UNREADABLE_TEXT = ('This part of the document is stored in a format MedUI can\'t open. '
                    'Open it in Best Practice.')


def _warn_unreadable(where: str, exc: Exception) -> None:
    if has_app_context():
        current_app.logger.warning('document_service: %s unreadable: %s', where, type(exc).__name__)


_HTML_UNREADABLE = DocumentResult(
    'html',
    f'<p style="color:var(--text-muted);padding:1rem;">{_UNREADABLE_TEXT}</p>',
    'text/html; charset=utf-8',
)


# ── Format converters ─────────────────────────────────────────────────────────

def _rtf_to_html(data: bytes | str) -> str:
    """Convert RTF bytes/string to a safe HTML fragment."""
    try:
        from striprtf.striprtf import rtf_to_text
    except ImportError:
        return '<pre>RTF rendering requires the striprtf package.</pre>'

    if isinstance(data, bytes):
        rtf_str = data.decode('cp1252', errors='replace')
    else:
        rtf_str = data

    try:
        text = rtf_to_text(rtf_str)
    except Exception as exc:
        current_app.logger.warning('rtf_to_text failed: %s', exc)
        text = rtf_str

    escaped = html_lib.escape(text)
    return f'<pre style="white-space:pre-wrap;font-family:monospace;font-size:0.85rem;">{escaped}</pre>'


def _tif_to_png(data: bytes) -> bytes | None:
    """Convert TIF/TIFF bytes to PNG bytes via Pillow."""
    try:
        from PIL import Image
    except ImportError:
        current_app.logger.error('Pillow not installed — cannot convert TIF to PNG.')
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
    except Exception as exc:
        current_app.logger.error('TIF→PNG conversion failed: %s', exc)
        return None


def _tif_pages(data: bytes) -> int:
    """Number of pages (frames) in a TIFF; 1 if it can't be read."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as img:
            return getattr(img, 'n_frames', 1) or 1
    except Exception:  # Pillow raises several types for bad images; one page is the safe answer
        return 1


def _wrap_html(body_html: str, title: str = '') -> str:
    """Wrap an HTML fragment in a minimal standalone document for the viewer iframe."""
    escaped_title = html_lib.escape(title)
    return (
        '<!DOCTYPE html><html><head>'
        '<meta charset="utf-8">'
        f'<title>{escaped_title}</title>'
        '<style>'
        'body{font-family:sans-serif;padding:1.25rem;line-height:1.5;'
        'background:#fff;color:#222;margin:0;}'
        'pre{white-space:pre-wrap;word-break:break-word;}'
        '.report-header{margin-bottom:0.75rem;padding-bottom:0.75rem;'
        'border-bottom:1px solid #ddd;}'
        '</style>'
        f'</head><body>{body_html}</body></html>'
    )


# ── Core dispatch ─────────────────────────────────────────────────────────────

def _detect_and_render(data: bytes, doctype: str = '', compression: int = 0) -> DocumentResult:
    """Format detection and rendering dispatch.  doctype is uppercased by caller."""

    # ZIP extraction — Compression==1 flag OR PK magic bytes
    if compression == 1 or (not doctype and data[:2] == b'PK'):
        try:
            with ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if not names:
                    return _HTML_EMPTY

                # CDA takes priority
                cda = next((n for n in names if n.upper() == 'CDA_ROOT.XML'), None)
                if cda or doctype == 'CDA':
                    xml_data = z.read(cda or names[0])
                    html_out = _cda_to_html(xml_data)
                    if html_out:
                        return DocumentResult('html', html_out, 'text/html; charset=utf-8')
                    escaped = html_lib.escape(xml_data.decode('utf-8', errors='replace'))
                    return DocumentResult('html', _wrap_html(f'<pre>{escaped}</pre>'), 'text/html; charset=utf-8')

                first     = names[0]
                inner     = z.read(first)
                ext       = first.rsplit('.', 1)[-1].upper() if '.' in first else ''
                return _detect_and_render(inner, doctype=ext, compression=0)
        except BadZipFile:
            pass  # Not actually a ZIP — fall through
        except _UNPACK_ERRORS as exc:
            _warn_unreadable('ZIP content', exc)
            return _HTML_UNREADABLE

    dt = doctype.upper()

    # PDF
    if dt == 'PDF' or data[:4] == b'%PDF':
        return DocumentResult('pdf', data, 'application/pdf')

    # Images
    if dt in ('TIF', 'TIFF'):
        png = _tif_to_png(data)
        if png:
            # OCR reads the original only when it has more than one page: the
            # display PNG holds page 1 alone. A single page reads better as the
            # PNG — 2,431 vs 2,077 real words on 25 BP fax TIFFs (2026-10-05),
            # while 5 multi-page TIFFs went from 599 to 1,094.
            if _tif_pages(data) > 1:
                return DocumentResult('image', png, 'image/png', ocr_source=data, ocr_mime='image/tiff')
            return DocumentResult('image', png, 'image/png')
        return DocumentResult('html', _wrap_html('<p>Could not convert TIFF for display.</p>'), 'text/html; charset=utf-8')
    if dt == 'BMP':
        return DocumentResult('image', data, 'image/bmp')
    if dt in ('JPG', 'JPEG'):
        return DocumentResult('image', data, 'image/jpeg')
    if dt == 'PNG':
        return DocumentResult('image', data, 'image/png')

    # HTML
    if dt in ('HTML', 'HTM'):
        return DocumentResult('html', data.decode('utf-8', errors='replace'), 'text/html; charset=utf-8')

    # RTF (explicit or auto-detect by magic bytes)
    if dt == 'RTF' or data[:5] == b'{\\rtf':
        return DocumentResult('html', _wrap_html(_rtf_to_html(data)), 'text/html; charset=utf-8')

    # CDA / XML
    if dt in ('CDA', 'XML') or data[:5] == b'<?xml':
        html_out = _cda_to_html(data)
        if html_out:
            return DocumentResult('html', html_out, 'text/html; charset=utf-8')
        escaped = html_lib.escape(data.decode('utf-8', errors='replace'))
        return DocumentResult('html', _wrap_html(f'<pre>{escaped}</pre>'), 'text/html; charset=utf-8')

    # Fallback: UTF-8 text
    try:
        text    = data.decode('utf-8', errors='replace')
        escaped = html_lib.escape(text)
        return DocumentResult('html', _wrap_html(f'<pre>{escaped}</pre>'), 'text/html; charset=utf-8')
    except Exception:
        return DocumentResult('html', _wrap_html('<p>Unsupported document format.</p>'), 'text/html; charset=utf-8')


# ── Public API ────────────────────────────────────────────────────────────────

def render_letter(binary: bytes | None) -> DocumentResult:
    """Process letter binary (typically RTF stored in BPSDocuments{N}.dbo.LETTERS)."""
    if binary is None:
        return _HTML_UNAVAILABLE
    if not binary:
        return _HTML_EMPTY
    return _detect_and_render(binary)


def render_scan(binary: bytes | None, doctype: str = '', compression: int = 0) -> DocumentResult:
    """Process scan/document binary with its declared DocType and Compression flag."""
    if binary is None:
        return _HTML_UNAVAILABLE
    if not binary:
        return _HTML_EMPTY
    return _detect_and_render(binary, doctype=doctype.upper(), compression=compression)


def render_path_report(
    header_rtf: bytes | str | None,
    body_rtf:   bytes | str | None,
    binary:     bytes | None = None,
) -> DocumentResult:
    """Render a pathology report from RTF header/body fields and optional binary attachment.

    Both REPORTHEADER and REPORTBODY may themselves be stored as ZIP archives —
    this is handled by _safe_rtf().

    If a binary attachment (from BPSDocuments{N}.dbo.INVESTIGATIONS) is present
    and is a PDF or image, it takes priority and the RTF header/body are discarded
    (legacy Best Practice behaviour — the binary is the actual report; RTF is metadata).
    """

    def _safe_rtf(raw) -> str:
        if not raw:
            return ''
        # Both header and body can be ZIP-compressed in BPSDB
        if isinstance(raw, bytes) and raw[:2] == b'PK':
            try:
                with ZipFile(io.BytesIO(raw)) as z:
                    return ''.join(_rtf_to_html(z.read(n)) for n in z.namelist())
            except BadZipFile:
                pass
            except _UNPACK_ERRORS as exc:
                _warn_unreadable('report field', exc)
                return f'<p style="color:var(--text-muted);">{_UNREADABLE_TEXT}</p>'
        return _rtf_to_html(raw)

    parts: list[str] = []

    header_html = _safe_rtf(header_rtf)
    body_html   = _safe_rtf(body_rtf)

    if header_html:
        parts.append(f'<div class="report-header">{header_html}</div>')
    if body_html:
        parts.append(f'<div class="report-body">{body_html}</div>')

    if binary:
        binary_result = _detect_and_render(binary)
        if binary_result.render_type in ('pdf', 'image'):
            # Binary wins — it is the actual report content
            return binary_result
        elif binary_result.render_type == 'html':
            parts.append(f'<div class="report-binary">{binary_result.content}</div>')

    if not parts:
        return _HTML_EMPTY

    return DocumentResult('html', _wrap_html('\n'.join(parts)), 'text/html; charset=utf-8')


# ── Plain-text extraction ────────────────────────────────────────────────────

def extract_text(result: DocumentResult) -> str:
    """Convert a DocumentResult to plain text suitable for AI input.

    For HTML results (RTF, CDA, plain text) tags are stripped locally.
    For PDF and image results the external OCR service (liteparse) is tried
    first; if unavailable a descriptive placeholder is returned instead.
    """
    if result.render_type in ('pdf', 'image'):
        if isinstance(result.content, (bytes, bytearray)) and result.content:
            try:
                from app.services import ocr_service
                # The original when there is one (a TIFF, not its display PNG).
                source = result.ocr_source or result.content
                mime = result.ocr_mime or result.mimetype.split(';')[0].strip()
                extracted = ocr_service.extract_text(bytes(source), mimetype=mime)
                if extracted:
                    return extracted
            except Exception as exc:
                current_app.logger.warning('extract_text OCR call failed: %s', exc)
        # OCR unavailable or returned nothing
        if result.render_type == 'pdf':
            return '[PDF document — configure OCR service for text extraction]'
        return '[Image document — configure OCR service for text extraction]'

    # HTML result — strip tags to get plain text
    content = result.content
    if isinstance(content, bytes):
        content = content.decode('utf-8', errors='replace')
    # Remove style/script blocks entirely (content included, not just the tags)
    content = re.sub(r'<style\b[^>]*>.*?</style>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<script\b[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)

    # <pre> blocks (pathology report headers, and cumulative result tables that align
    # columns using literal spaces/tabs) carry meaningful whitespace — stash them so the
    # collapsing below doesn't scramble that alignment, then restore verbatim.
    # Lab HTML reports can put markup inside the <pre> (<br> for every line break, <font>
    # around flagged values), so tags are removed there too — <br> first, as a newline —
    # before entities are decoded. Our own <pre> blocks (RTF, plain text) are escaped and
    # hold no tags, so they come back as before.
    pre_blocks: list[str] = []

    def _stash_pre(m: re.Match) -> str:
        inner = re.sub(r'<br\s*/?>', '\n', m.group(1), flags=re.IGNORECASE)
        inner = re.sub(r'<[^>]+>', '', inner)
        pre_blocks.append(html_lib.unescape(inner).strip('\n'))
        return f'\x00PRE{len(pre_blocks) - 1}\x00'

    content = re.sub(r'<pre\b[^>]*>(.*?)</pre>', _stash_pre, content, flags=re.IGNORECASE | re.DOTALL)

    content = re.sub(r'<br\s*/?>', '\n', content, flags=re.IGNORECASE)
    content = re.sub(r'</(?:p|div|li|tr|h[1-6])>', '\n', content, flags=re.IGNORECASE)
    content = re.sub(r'<[^>]+>', '', content)
    content = html_lib.unescape(content)
    content = re.sub(r'[ \t]+', ' ', content)
    content = re.sub(r'\n[ \t]+', '\n', content)
    content = re.sub(r'\n{3,}', '\n\n', content)

    for i, block in enumerate(pre_blocks):
        content = content.replace(f'\x00PRE{i}\x00', '\n' + block + '\n')

    return content.strip()
