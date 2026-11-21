"""Outbound SMS via email-to-SMS gateway."""
from __future__ import annotations
import re
import smtplib
import unicodedata
import email.message

from flask import current_app
from app.models.system_setting import SystemSetting


def _get_secret(key: str) -> str:
    raw = SystemSetting.get(key, '')
    if not raw:
        return ''
    try:
        from app.utils.crypto import decrypt_secret
        return decrypt_secret(raw)
    except Exception:
        return ''


def _set_secret(key: str, plaintext: str) -> None:
    from app.utils.crypto import encrypt_secret
    SystemSetting.set(key, encrypt_secret(plaintext))


def _get_config() -> dict:
    return {
        'smtp_host':          SystemSetting.get('sms.smtp_host', ''),
        'smtp_port':          SystemSetting.get('sms.smtp_port', 25),
        'sender_address':     SystemSetting.get('sms.sender_address', ''),
        'recipient_template': SystemSetting.get('sms.recipient_template', ''),
        'requires_auth':      SystemSetting.get('sms.requires_auth', False),
        'smtp_username':      SystemSetting.get('sms.smtp_username', ''),
        'smtp_password':      _get_secret('sms.smtp_password'),
        'use_tls':            SystemSetting.get('sms.use_tls', False),
    }


# Email-to-SMS gateways can accept an email with non-ASCII text (sent as UTF-8, 8bit) and then not
# deliver it, with no error back (ADR-160). Typographic punctuation, common in drafted text, becomes
# its plain equivalent and accented letters lose their accents; nothing else is changed.
_PLAIN = str.maketrans({
    '\u2014': '-', '\u2013': '-', '\u2012': '-', '\u2010': '-', '\u2011': '-', '\u2212': '-',
    '\u2018': "'", '\u2019': "'", '\u201a': "'", '\u2032': "'",
    '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u2033': '"',
    '\u2026': '...', '\u2022': '-',
    '\u00a0': ' ', '\u2007': ' ', '\u2009': ' ', '\u202f': ' ',
    '\u200b': '', '\u200c': '', '\u200d': '', '\ufeff': '',
})


def plain_text(text: str) -> str:
    """The SMS text as the gateway is sent it: plain ASCII where the text allows."""
    text = text.translate(_PLAIN)
    if text.isascii():
        return text
    out = []
    for ch in text:
        if ch.isascii():
            out.append(ch)
            continue
        base = ''.join(c for c in unicodedata.normalize('NFKD', ch) if not unicodedata.combining(c))
        out.append(base if base and base.isascii() else ch)
    return ''.join(out)


def send(mobile_number: str, message: str) -> None:
    """Send SMS via email-to-SMS gateway. Raises RuntimeError on failure."""
    cfg = _get_config()
    _validate(cfg)

    number = re.sub(r'\D', '', mobile_number)
    to_address = cfg['recipient_template'].replace('{number}', number)

    msg = email.message.EmailMessage()
    text = plain_text(message)
    if not text.isascii():
        current_app.logger.warning('sms_service: message has characters the gateway may not deliver')
    msg.set_content(text)
    msg['From']    = cfg['sender_address']
    msg['To']      = to_address
    msg['Subject'] = ''

    _smtp_send(cfg, to_address, msg)
    current_app.logger.info('sms_service: sent to %s (mobile %s)', to_address, mobile_number)


def test(mobile_number: str) -> dict:
    """Send a test SMS. Returns {'ok': bool, 'message': str}."""
    try:
        cfg = _get_config()
        number = re.sub(r'\D', '', mobile_number)
        gateway = cfg.get('recipient_template', '').replace('{number}', number)
        send(mobile_number, 'MedUI test message - please ignore.')
        return {'ok': True, 'message': f'Dispatched to gateway address: {gateway}'}
    except RuntimeError as e:
        return {'ok': False, 'message': str(e)}


def is_configured() -> bool:
    cfg = _get_config()
    return bool(
        cfg.get('smtp_host') and
        cfg.get('sender_address') and
        cfg.get('recipient_template') and
        '{number}' in cfg.get('recipient_template', '')
    )


def sms_password_is_set() -> bool:
    return bool(SystemSetting.get('sms.smtp_password', ''))


def _validate(cfg: dict) -> None:
    missing = []
    if not cfg.get('smtp_host'):
        missing.append('gateway host')
    if not cfg.get('sender_address'):
        missing.append('sender address')
    if not cfg.get('recipient_template'):
        missing.append('recipient template')
    elif '{number}' not in cfg['recipient_template']:
        missing.append('recipient template must contain {number}')
    if missing:
        raise RuntimeError(
            f"SMS not fully configured. Missing: {', '.join(missing)}. "
            "Configure under Setup → Messaging."
        )


def _smtp_send(cfg: dict, to_address: str, msg: email.message.EmailMessage) -> None:
    from flask import current_app
    if not current_app.config.get('MESSAGING_ENABLED', False):
        raise RuntimeError('Outbound messaging is disabled for this installation.')
    try:
        smtp = smtplib.SMTP(cfg['smtp_host'], int(cfg['smtp_port']), timeout=30)
        smtp.ehlo()
        if cfg.get('requires_auth'):
            if cfg.get('use_tls'):
                smtp.starttls()
                smtp.ehlo()
            smtp.login(cfg['smtp_username'], cfg['smtp_password'])
        smtp.send_message(msg)
        smtp.quit()
    except smtplib.SMTPException as e:
        current_app.logger.error('sms_service SMTP error: %s', e)
        raise RuntimeError(f'Failed to send SMS: {e}') from e
    except OSError as e:
        current_app.logger.error('sms_service network error: %s', e)
        raise RuntimeError(f'Network error sending SMS: {e}') from e
