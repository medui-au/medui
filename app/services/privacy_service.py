"""privacy_service — staff record access control.

When privacy.hide_staff_records is enabled in Setup → Maintenance, any patient
whose InternalId is linked to a staff user (via bpsdb_internal_id) can only be
opened by that staff member themselves or by a security_level >= 9 admin.

The bpsdb_internal_id mapping is populated by:
    flask seed sync-bpsdb-users
or set manually in Setup → Users.
"""
import time
from flask import abort
from flask_login import current_user

_CACHE_TTL = 60  # seconds — re-read setting from DB at most once per minute
_setting_cache: dict = {'value': None, 'expires': 0.0}


def _privacy_enabled() -> bool:
    now = time.monotonic()
    if now < _setting_cache['expires']:
        return bool(_setting_cache['value'])
    from app.models.system_setting import SystemSetting
    val = SystemSetting.get('privacy.hide_staff_records', False)
    _setting_cache['value'] = val
    _setting_cache['expires'] = now + _CACHE_TTL
    return bool(val)


def check_patient_access(patient_id: int) -> None:
    """Abort 403 if the current user is not permitted to view this patient record.

    No-op when:
      - privacy.hide_staff_records is disabled
      - the patient is not linked to any staff user
      - the current user IS the staff member whose record this is
      - the current user has security_level >= 9
    """
    if not _privacy_enabled():
        return

    from app.models.user import User
    owner = User.query.filter_by(
        bpsdb_internal_id=patient_id,
        is_active=True,
    ).first()

    if owner is None:
        return  # Not a protected staff record

    if owner.id == current_user.id:
        return  # Staff member viewing their own record

    if current_user.security_level >= 9:
        return  # Admin

    from werkzeug.exceptions import Forbidden
    raise Forbidden(description='privacy_protected')
