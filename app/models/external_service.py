from datetime import datetime, timezone
import enum
from app.extensions import db


class ExternalServiceType(str, enum.Enum):
    ocr = 'ocr'


class ExternalServiceConfig(db.Model):
    """Registry of external HTTP services (OCR)."""
    __tablename__ = 'external_service_configs'

    id                   = db.Column(db.Integer, primary_key=True)
    service_type         = db.Column(db.Enum(ExternalServiceType), nullable=False)
    display_name         = db.Column(db.String(120), nullable=False)
    base_url             = db.Column(db.String(500), nullable=False)
    health_check_path    = db.Column(db.String(200), default='/health')
    api_path             = db.Column(db.String(500))  # OCR parsing endpoint, normally /parse
    # Optional auth — header name + Fernet-encrypted key value
    auth_header_name     = db.Column(db.String(80), default='X-API-KEY')
    api_key_enc          = db.Column(db.String(500))
    is_enabled           = db.Column(db.Boolean, nullable=False, default=True)
    last_health_check_at = db.Column(db.DateTime)
    last_health_check_ok = db.Column(db.Boolean)
    notes                = db.Column(db.Text)

    @property
    def api_key(self) -> str | None:
        if not self.api_key_enc:
            return None
        from app.utils.crypto import decrypt_secret
        return decrypt_secret(self.api_key_enc)

    @api_key.setter
    def api_key(self, plaintext: str | None) -> None:
        if plaintext:
            from app.utils.crypto import encrypt_secret
            self.api_key_enc = encrypt_secret(plaintext)
        else:
            self.api_key_enc = None

    def __repr__(self) -> str:
        return f'<ExternalServiceConfig {self.service_type} {self.display_name}>'
