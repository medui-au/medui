"""Generate installation secrets once, without overwriting an existing .env."""
from pathlib import Path
import os
import base64
import secrets

root = Path(__file__).resolve().parents[1]
password = secrets.token_hex(24)
values = {
    'POSTGRES_PASSWORD': password,
    'DATABASE_URL': f'postgresql://medui:{password}@127.0.0.1:55432/medui',
    'SECRET_KEY': secrets.token_hex(32),
    # A Fernet key is 32 random bytes, URL-safe base64: no third-party package
    # needed, so a fresh host can run this with its own python3.
    'MEDUI_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
}
lines = (root / '.env.example').read_text().splitlines()
content = '\n'.join(f'{line.split("=", 1)[0]}={values[line.split("=", 1)[0]]}'
                    if '=' in line and line.split('=', 1)[0] in values else line
                    for line in lines) + '\n'
try:
    fd = os.open(root / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit('.env already exists; left unchanged.')
with os.fdopen(fd, 'w') as f:
    f.write(content)
print('Created .env with fresh secrets. Set your practice BP connection before using clinical features.')
