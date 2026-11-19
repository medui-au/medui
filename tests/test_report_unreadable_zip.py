"""A report or document whose ZIP opens but can't be unpacked shows a message, not a 500.

BP's sample databases store some pathology REPORTHEADER/REPORTBODY fields as Deflate64
(zip method 9), which Python's zipfile can't read: it raises NotImplementedError. The report
below is invented.
"""
import io
from zipfile import ZipFile

from app.services import document_service as ds


def _zipped(name: str, data: bytes, method: int | None = None) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as z:
        z.writestr(name, data)
    raw = bytearray(buf.getvalue())
    if method is not None:  # rewrite the method in the local and central headers
        raw[8:10] = method.to_bytes(2, 'little')
        c = raw.find(b'PK\x01\x02')
        raw[c + 10:c + 12] = method.to_bytes(2, 'little')
    return bytes(raw)


_RTF = b'{\\rtf1\\ansi Invented report: Haemoglobin 140 g/L}'


def test_deflate64_report_body_shows_a_message():
    result = ds.render_path_report(_zipped('H.RTF', _RTF), _zipped('B.RTF', _RTF, method=9))
    assert result.render_type == 'html'
    assert "format MedUI can't open" in result.content
    assert 'Invented report' in result.content  # the readable header still shows


def test_deflate64_scan_shows_a_message():
    result = ds.render_scan(_zipped('X.PDF', b'%PDF-1.4 invented', method=9), compression=1)
    assert result.render_type == 'html'
    assert "format MedUI can't open" in result.content


def test_ordinary_zip_still_renders():
    result = ds.render_path_report(None, _zipped('B.RTF', _RTF))
    assert 'Invented report' in result.content
    assert "can't open" not in result.content
