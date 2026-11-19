"""Exercise configured OCR using an in-memory, synthetic scanned page."""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from app import create_app
from app.services import ocr_service

image = Image.new('RGB', (1400, 350), 'white')
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=48)
draw.text((50, 60), 'MEDUI OCR TEST', font=font, fill='black')
draw.text((50, 160), 'Synthetic document with no patient data.', font=font, fill='black')
stream = io.BytesIO()
image.save(stream, format='PNG')
with create_app().app_context():
    result = ocr_service.extract_text(stream.getvalue(), 'image/png', 'synthetic.png')
if not result or 'MEDUI' not in result.upper() or 'SYNTHETIC' not in result.upper():
    raise SystemExit('OCR smoke test failed; inspect the local OCR service.')
print('Synthetic scanned-image OCR passed.')
