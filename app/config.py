"""Installation-local configuration. Process environment overrides project .env."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)


def _bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in ('1', 'true', 'yes')


def _odbc(value):
    return '{' + value.replace('}', '}}') + '}'


def _build_bpsdb_connection_string():
    if os.environ.get('BPSDB_URI'):
        return os.environ['BPSDB_URI']
    host = os.environ.get('BPSDB_HOST', '').strip()
    # Not configured unless the server, login and password are all given (ADR-140): a login
    # with a blank one would only fail, and "not configured" sends an administrator's login to
    # Setup → Database.
    if not host or not os.environ.get('BPSDB_USER', '').strip() or not os.environ.get('BPSDB_PASSWORD', ''):
        return None
    values = {
        'DRIVER': os.environ.get('BPSDB_DRIVER', 'ODBC Driver 18 for SQL Server'),
        'SERVER': host,
        'DATABASE': os.environ.get('BPSDB_DATABASE', 'BPSPatients'),
        'UID': os.environ.get('BPSDB_USER', ''),
        'PWD': os.environ.get('BPSDB_PASSWORD', ''),
    }
    return ''.join(f'{k}={_odbc(v)};' for k, v in values.items()) + (
        'Encrypt=yes;TrustServerCertificate=' +
        ('yes' if _bool('BPSDB_TRUST_SERVER_CERTIFICATE') else 'no') + ';'
    )


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', '')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    BPSDB_URI = _build_bpsdb_connection_string()
    SCRIBE_ENCRYPTION_KEY = os.environ.get('MEDUI_ENCRYPTION_KEY')
    APP_NAME = os.environ.get('APP_NAME', 'MedUI')
    TEMP_DIR = os.environ.get('TEMP_DIR', '/tmp/medui')
    PRACTICE_TIMEZONE = os.environ.get('PRACTICE_TIMEZONE', 'Australia/Brisbane')
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 43200
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _bool('SESSION_COOKIE_SECURE')
    PATIENT_API_ENABLED = _bool('PATIENT_API_ENABLED')
    PATIENT_API_KEYS = [v for v in [os.environ.get('PATIENT_API_KEY')] if v]
    PBS_API_KEY = os.environ.get('PBS_API_KEY', '')
    OCR_ENABLED = _bool('OCR_ENABLED', True)   # missing (an older .env): on, as before
    OCR_SERVICE_URL = os.environ.get('OCR_SERVICE_URL', '')
    OCR_API_KEY = os.environ.get('OCR_API_KEY', '')
    OCR_CA_BUNDLE = os.environ.get('OCR_CA_BUNDLE') or True
    OCR_TIMEOUT = int(os.environ.get('OCR_TIMEOUT', '150'))
    AI_ENABLED = _bool('AI_ENABLED')
    MESSAGING_ENABLED = _bool('MESSAGING_ENABLED')
    PIT_EXPORT_ENABLED = _bool('PIT_EXPORT_ENABLED')

    @classmethod
    def validate(cls):
        from cryptography.fernet import Fernet
        from sqlalchemy.engine import make_url
        errors = []
        if not cls.SQLALCHEMY_DATABASE_URI:
            errors.append('DATABASE_URL is required in the project .env or environment')
        elif make_url(cls.SQLALCHEMY_DATABASE_URI).get_backend_name() != 'postgresql':
            errors.append('This release requires PostgreSQL')
        if len(cls.SECRET_KEY) < 32:
            errors.append('SECRET_KEY must contain at least 32 characters')
        try:
            Fernet(cls.SCRIBE_ENCRYPTION_KEY or '')
        except (ValueError, TypeError):
            errors.append('MEDUI_ENCRYPTION_KEY must be a valid Fernet key')
        try:
            ZoneInfo(cls.PRACTICE_TIMEZONE)
        except (KeyError, ValueError):
            errors.append('PRACTICE_TIMEZONE must be a valid IANA timezone')
        if errors:
            raise RuntimeError('Configuration errors: ' + '; '.join(errors))


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config_map = {'dev': DevelopmentConfig, 'development': DevelopmentConfig,
              'prod': ProductionConfig, 'production': ProductionConfig}
