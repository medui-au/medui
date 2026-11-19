"""Fernet-based transparent column encryption for SQLAlchemy.

Usage:
    from app.utils.encrypted_type import EncryptedText

    class MyModel(db.Model):
        sensitive_field = db.Column(EncryptedText(), nullable=True)

The stored value is a Fernet token (base64 URL-safe string).
Reading returns the original plaintext (str or None).

If MEDUI_ENCRYPTION_KEY is absent, any read/write raises RuntimeError
so that unencrypted data is never silently stored.
"""
import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator


def _get_fernet() -> Fernet:
    from app.utils.crypto import _fernet
    return _fernet()


class EncryptedText(TypeDecorator):
    """Transparently encrypts/decrypts a text column using Fernet (AES-128-CBC + HMAC)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        return f.encrypt(value.encode('utf-8')).decode('ascii')

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        f = _get_fernet()
        try:
            return f.decrypt(value.encode('utf-8')).decode('utf-8')
        except (InvalidToken, Exception):
            # Row predates encryption — return as-is so old rows remain readable
            return value
