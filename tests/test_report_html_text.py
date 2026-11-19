"""Plain text from a lab report stored as HTML: tags inside its <pre> are removed too.

Some inbox results arrive as a zipped .HTML file whose whole report is one <pre> that uses
<br> for every line break and <font> around flagged values. The Results Rollup copied that
markup as one long line. The report below is invented.
"""
import io
from zipfile import ZipFile

from app.services import document_service as ds

_INVENTED_HTML = (
    '<html><head><!--invented--><style>.x{color:red}</style></head><body>'
    '<table><tr><td><b>Example Lab</b></td></tr></table>'
    '<pre>TEST NAME: FULL BLOOD COUNT<br>'
    'Haemoglobin   <font color="red">98</font>  g/L   (115-165)<br>'
    'Platelets     250  x10^9/L (150-400)<br/>'
    'Comment: result &lt;3 &amp; repeat in 6 weeks</pre>'
    '</body></html>'
)


def _zipped(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, 'w') as z:
        z.writestr(name, data)
    return buf.getvalue()


def test_html_report_in_a_zip_copies_as_plain_lines():
    result = ds.render_path_report(None, None, binary=_zipped('REPORT.HTML', _INVENTED_HTML.encode()))
    text = ds.extract_text(result)
    assert '<' not in text.replace('<3', '') and 'font' not in text and 'color:red' not in text
    lines = text.splitlines()
    assert 'TEST NAME: FULL BLOOD COUNT' in lines
    assert 'Haemoglobin   98  g/L   (115-165)' in lines  # spacing inside <pre> kept
    assert 'Platelets     250  x10^9/L (150-400)' in lines
    assert 'Comment: result <3 & repeat in 6 weeks' in lines
    assert text.startswith('Example Lab')


def test_escaped_pre_from_rtf_is_unchanged():
    # Our own RTF/plain-text rendering escapes the text, so a literal "<b>" written in a
    # report stays as typed rather than being treated as a tag.
    rtf = r'{\rtf1\ansi Value <b> stays\par Line two\par}'
    text = ds.extract_text(ds.render_path_report(None, rtf))
    assert '<b> stays' in text and 'Line two' in text


def test_plain_text_binary_is_unchanged():
    data = b'Col A\tCol B\n  1      2\nnote: a < b'
    text = ds.extract_text(ds.render_path_report(None, None, binary=_zipped('R.TXT', data)))
    assert text == 'Col A\tCol B\n  1      2\nnote: a < b'
