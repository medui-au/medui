"""Outbound email service using SMTP."""
from __future__ import annotations
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

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
        'smtp_host':      SystemSetting.get('email.smtp_host', ''),
        'smtp_port':      SystemSetting.get('email.smtp_port', 587),
        'smtp_username':  SystemSetting.get('email.smtp_username', ''),
        'smtp_password':  os.environ.get('EMAIL_SMTP_PASSWORD') or _get_secret('email.smtp_password'),
        'sender_name':    SystemSetting.get('email.sender_name', ''),
        'sender_address': SystemSetting.get('email.sender_address', ''),
        'use_tls':        SystemSetting.get('email.use_tls', True),
    }


def send(to_address: str, subject: str, body: str,
         to_name: str = '', use_html: bool = False) -> None:
    """Send email via configured SMTP. Raises RuntimeError on failure or misconfiguration."""
    cfg = _get_config()
    _validate(cfg)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = formataddr((cfg['sender_name'], cfg['sender_address']))
    msg['To']      = formataddr((to_name, to_address)) if to_name else to_address

    if use_html:
        try:
            import markdown as md
            html_body = md.markdown(body, extensions=['tables'])
        except ImportError:
            html_body = f'<pre>{body}</pre>'
        msg.attach(MIMEText(body,      'plain', 'utf-8'))
        msg.attach(MIMEText(html_body, 'html',  'utf-8'))
    else:
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

    _smtp_send(cfg, to_address, msg.as_string())
    current_app.logger.info('email_service: sent to %s subject=%r', to_address, subject)


def test_connection(host: str, port: int, username: str, password: str,
                    use_tls: bool, sender: str) -> dict:
    """Test SMTP login with supplied credentials. Returns {'ok': bool, 'message': str}."""
    try:
        smtp = smtplib.SMTP(host, int(port), timeout=10)
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(username, password)
        smtp.quit()
        return {'ok': True, 'message': f'Connected and authenticated to {host}:{port}.'}
    except smtplib.SMTPAuthenticationError:
        return {'ok': False, 'message': 'Authentication failed — check username and password.'}
    except smtplib.SMTPConnectError as e:
        return {'ok': False, 'message': f'Could not connect to {host}:{port} — {e}'}
    except OSError as e:
        return {'ok': False, 'message': f'Network error: {e}'}
    except Exception as e:
        return {'ok': False, 'message': str(e)}


def is_configured() -> bool:
    cfg = _get_config()
    return bool(cfg.get('smtp_host') and cfg.get('smtp_username') and cfg.get('sender_address'))


def password_is_set() -> bool:
    return bool(SystemSetting.get('email.smtp_password', ''))


def password_from_env() -> bool:
    return bool(os.environ.get('EMAIL_SMTP_PASSWORD'))


def _validate(cfg: dict) -> None:
    missing = [
        label for label, key in (
            ('SMTP host',       'smtp_host'),
            ('SMTP username',   'smtp_username'),
            ('SMTP password',   'smtp_password'),
            ('sender address',  'sender_address'),
        ) if not cfg.get(key)
    ]
    if missing:
        raise RuntimeError(
            f"Email not fully configured. Missing: {', '.join(missing)}. "
            "Configure under Setup → Messaging."
        )


def _smtp_send(cfg: dict, to_address: str, msg_string: str) -> None:
    from flask import current_app
    if not current_app.config.get('MESSAGING_ENABLED', False):
        raise RuntimeError('Outbound messaging is disabled for this installation.')
    try:
        smtp = smtplib.SMTP(cfg['smtp_host'], int(cfg['smtp_port']), timeout=30)
        smtp.ehlo()
        if cfg['use_tls']:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(cfg['smtp_username'], cfg['smtp_password'])
        smtp.sendmail(cfg['sender_address'], to_address, msg_string)
        smtp.quit()
    except smtplib.SMTPException as e:
        current_app.logger.error('email_service SMTP error: %s', e)
        raise RuntimeError(f'Failed to send email: {e}') from e
    except OSError as e:
        current_app.logger.error('email_service network error: %s', e)
        raise RuntimeError(f'Network error sending email: {e}') from e
