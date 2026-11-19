"""Practice API blueprint — REST API for practice-centric administrative data.

All endpoints require a valid API key (Bearer token or X-Api-Key header)
or an active authenticated session. Shares the same key infrastructure as
the patient API (PATIENT_API_KEYS / patient_api_enabled).

Routes
------
GET /api/practice/reminders/due    Reminders due this month and next
"""

import functools

from flask import jsonify, request, current_app
from flask_login import current_user

from . import bp
from app.services.practice_service import PracticeService


# ── Auth guard ────────────────────────────────────────────────────────────────

def _api_enabled() -> bool:
    try:
        from app.models.system_settings import SystemSettings
        setting = SystemSettings.query.filter_by(key='patient_api_enabled').first()
        if setting:
            return setting.value in ('1', 'true', 'True', True)
    except Exception:
        pass
    return current_app.config.get('PATIENT_API_ENABLED', False)


def _check_api_key() -> bool:
    valid_keys: list[str] = current_app.config.get('PATIENT_API_KEYS', [])
    if not valid_keys:
        return False
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:].strip() in valid_keys
    return request.headers.get('X-Api-Key', '').strip() in valid_keys


def api_required(f):
    """Decorator: gate on API enabled + valid key OR active session."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not _api_enabled():
            return jsonify({'error': 'Practice API is not enabled.'}), 403
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        if not _check_api_key():
            return jsonify({'error': 'Unauthorized. Provide a valid API key.'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Routes ────────────────────────────────────────────────────────────────────

@bp.get('/reminders/due')
@api_required
def reminders_due():
    """Reminders due this month and next, excluding health assessments."""
    try:
        data = PracticeService.get_reminders_due()
    except Exception as exc:
        current_app.logger.error('practice_api.reminders_due: %s', exc)
        return jsonify({'error': 'Data retrieval failed.'}), 500
    return jsonify({'count': len(data), 'data': data})
