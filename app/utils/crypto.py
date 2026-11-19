"""Fernet-based symmetric encryption for secrets stored in the database (e.g. provider API keys).

Uses SCRIBE_ENCRYPTION_KEY from app config — the same key already used for transcript encryption.
Returns URL-safe base64 ciphertext strings safe to store in a VARCHAR column.
"""

from __future__ import annotations


def _fernet():
    from flask import current_app
    from cryptography.fernet import Fernet
    key = current_app.config.get('SCRIBE_ENCRYPTION_KEY')
    if not key:
        raise RuntimeError('SCRIBE_ENCRYPTION_KEY is not configured')
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret and return a URL-safe base64 ciphertext string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    """Decrypt a ciphertext string. Returns None if ciphertext is falsy or decryption fails."""
    if not ciphertext:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return None
