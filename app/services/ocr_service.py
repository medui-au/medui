"""Local LiteParse OCR adapter; failures leave document viewing available."""
from types import SimpleNamespace
import io
from PIL import Image, ImageSequence, UnidentifiedImageError
import requests
from flask import current_app

_MIME_TO_EXT = {'application/pdf': 'pdf', 'image/png': 'png', 'image/jpeg': 'jpg',
                'image/bmp': 'bmp', 'image/tiff': 'tif'}
_A4_WIDTH_INCHES = 8.27


def _pdf_resolution(image):
    """The dpi to give an image's PDF page, so the page is paper-sized. Without it Pillow uses
    72 dpi, and a 200 dpi scan becomes a page 2.8 times too large, which OCR reads worse. A
    scanner's own dpi (100 to 1200) is kept; otherwise (a photo, often marked 72 or unmarked)
    the image is taken as A4 wide."""
    dpi = image.info.get('dpi')
    try:
        dpi = float(dpi[0] if isinstance(dpi, tuple) else dpi)
    except (TypeError, ValueError, IndexError):
        dpi = 0
    if 100 <= dpi <= 1200:
        return dpi
    return max(72.0, image.width / _A4_WIDTH_INCHES)


def _get_config():
    from app.models.external_service import ExternalServiceConfig, ExternalServiceType
    if not current_app.config.get('OCR_ENABLED', True):   # medui_os: OCR_ENABLED=false in .env
        return None
    cfg = (ExternalServiceConfig.query
           .filter_by(service_type=ExternalServiceType.ocr).order_by(ExternalServiceConfig.id).first())
    # A saved disabled service overrides environment defaults.
    if cfg:
        return cfg if cfg.is_enabled else None
    url = current_app.config.get('OCR_SERVICE_URL')
    if not url:
        return None
    return SimpleNamespace(base_url=url, api_path='/parse',
                           api_key=current_app.config.get('OCR_API_KEY'),
                           auth_header_name='X-API-KEY')


def is_configured():
    return _get_config() is not None


def extract_text(data: bytes, mimetype='application/octet-stream', filename='document'):
    if not data:
        return None
    cfg = _get_config()
    if not cfg:
        return None
    path = cfg.api_path or '/parse'
    if not path.startswith('/') or path.startswith('//'):
        current_app.logger.warning('OCR API path must be relative to its configured server')
        return None
    headers = {cfg.auth_header_name or 'X-API-KEY': cfg.api_key} if cfg.api_key else {}
    mime = mimetype.split(';')[0].strip()
    filename = filename if '.' in filename else filename + '.' + _MIME_TO_EXT.get(mime, 'bin')
    try:
        if mime.startswith('image/'):
            # Avoid upstream ImageMagick image->PDF policy restrictions. Preserve
            # all TIFF frames and flatten transparency onto white before OCR.
            with Image.open(io.BytesIO(data)) as image:
                resolution = _pdf_resolution(image)   # the first page's, before the frames move
                pages = []
                for frame in ImageSequence.Iterator(image):
                    rgba = frame.convert('RGBA')
                    page = Image.new('RGB', rgba.size, 'white')
                    page.paste(rgba, mask=rgba.getchannel('A'))
                    pages.append(page)
                output = io.BytesIO()
                pages[0].save(output, format='PDF', save_all=True, append_images=pages[1:],
                              resolution=resolution)
                data = output.getvalue()
                mime = 'application/pdf'
                filename = 'document.pdf'
        resp = requests.post(cfg.base_url.rstrip('/') + path,
                             params={'text': 'true'},
                             files={'file': (filename, data, mime)},
                             headers=headers,
                             # The LiteParse service allows 280 s and asks for at least 120 s; a
                             # multi-page document read whole takes longer (15 pages: about 18 s).
                             timeout=(5, current_app.config.get('OCR_TIMEOUT', 150)),
                             verify=current_app.config.get('OCR_CA_BUNDLE', True))
        resp.raise_for_status()
        # A wrong endpoint returning HTML/JSON must never become clinical text.
        if resp.headers.get('Content-Type', '').split(';')[0].strip() != 'text/plain':
            current_app.logger.warning('OCR returned an unexpected content type')
            return None
        return resp.text.strip() or None
    except (requests.RequestException, UnidentifiedImageError, OSError, ValueError):
        current_app.logger.warning('OCR text extraction unavailable')
        return None
