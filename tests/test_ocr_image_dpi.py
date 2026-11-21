"""Images go to LiteParse as a paper-sized PDF page (0.53.5).

Pillow writes 72 dpi unless told, so a 200 dpi scan became a page 2.8 times too large, and OCR
read it worse (an invented two-page TIFF: 52 of 57 numbers right at 72 dpi, 55 at its own dpi)."""
import io
import re
from types import SimpleNamespace

import pytest
from flask import Flask
from PIL import Image

from app.services import ocr_service

A4_PX_200 = (1654, 2339)          # A4 at 200 dpi


def _image(fmt, size=A4_PX_200, dpi=None, pages=1):
    frames = [Image.new('L', size, 255) for _ in range(pages)]
    out = io.BytesIO()
    kw = {'dpi': (dpi, dpi)} if dpi else {}
    if pages > 1:
        kw.update(save_all=True, append_images=frames[1:])
    frames[0].save(out, format=fmt, **kw)
    return out.getvalue()


@pytest.mark.parametrize('fmt, size, dpi, expected', [
    ('TIFF', A4_PX_200, 200, 200),            # a scanner's dpi is kept
    ('TIFF', (2480, 3508), 300, 300),
    ('JPEG', (1240, 1754), 72, 1240 / 8.27),  # a photo marked 72: taken as A4 wide
    ('PNG', (1240, 1754), None, 1240 / 8.27), # unmarked: the same
    ('PNG', (300, 400), None, 72),            # never below 72
])
def test_pdf_resolution(fmt, size, dpi, expected):
    with Image.open(io.BytesIO(_image(fmt, size, dpi))) as im:
        assert ocr_service._pdf_resolution(im) == pytest.approx(expected, abs=0.5)


def test_a_multi_page_scan_is_sent_as_a4_pages(monkeypatch):
    sent = {}

    def fake_post(url, params, files, headers, timeout, verify):
        sent['name'], sent['pdf'], sent['mime'] = files['file']
        return SimpleNamespace(raise_for_status=lambda: None, text='invented text',
                               headers={'Content-Type': 'text/plain; charset=utf-8'})

    monkeypatch.setattr(ocr_service, '_get_config', lambda: SimpleNamespace(
        base_url='http://127.0.0.1:5707', api_path='/parse', api_key='', auth_header_name=''))
    monkeypatch.setattr(ocr_service.requests, 'post', fake_post)
    with Flask(__name__).app_context():
        text = ocr_service.extract_text(_image('TIFF', dpi=200, pages=2), 'image/tiff', 'scan')
    assert text == 'invented text' and sent['mime'] == 'application/pdf'
    boxes = re.findall(rb'/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)\s*\]', sent['pdf'])
    assert len(boxes) == 2
    for w, h in boxes:                          # A4 is 595 x 842 points
        assert abs(float(w) - 595.5) < 2 and abs(float(h) - 842) < 2
