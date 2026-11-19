import hashlib
import hmac
from datetime import datetime, timezone
from flask import current_app
from app.extensions import db
from app.models.user import User


# BP group code → MedUI security level, set at every BP login. Only these
# groups may log in. AI needs level 5 (User.can_use_ai): doctors and the
# practice's administrators; nurses and reception use MedUI without AI.
LOGIN_GROUP_LEVELS = {
    1:  9,   # Practice Manager
    3:  9,   # Practice Owner
    4:  5,   # Doctor
    42: 5,   # Doctor (variant)
    5:  3,   # Practice Nurse    — patient files, no AI
    7:  2,   # Receptionist      — patient files, no AI
}


class AuthService:

    BP_SETUP_MESSAGE = ("The Best Practice database connection isn't set in this installation's "
                        "settings file yet, so MedUI has opened Setup → Database, which says what "
                        "to add. Restart MedUI after adding it.")

    @staticmethod
    def safe_next(next_url: str | None) -> str | None:
        """The ?next= address if it is a page of this site, else None (never another site)."""
        if not next_url:
            return None
        from urllib.parse import urlsplit
        if (not next_url.startswith('/') or next_url.startswith('//') or '\\' in next_url
                or any(ord(c) < 32 for c in next_url)):
            return None
        parts = urlsplit(next_url)
        return next_url if not parts.scheme and not parts.netloc else None

    @staticmethod
    def needs_bp_setup(user: User, next_url: str | None, setup_url: str) -> bool:
        """After login: send this user to Setup → Database instead?

        Only an administrator (the one who can fix the settings), only when Best Practice isn't
        configured, and not when ?next= already goes to a Setup page.
        """
        if not user.is_admin or current_app.config.get('BPSDB_URI'):
            return False
        return not (next_url or '').startswith(setup_url)

    @staticmethod
    def get_login_users() -> list[dict]:
        """Return [{name, value}] for the login dropdown.

        Tries BPSDB live first; falls back to Gen5 DB (seeded cache) on any failure.
        """
        try:
            uri = current_app.config.get('BPSDB_URI')
            if not uri:
                raise RuntimeError('BPSDB not configured')
            from app.sql.query_loader import ReadOnlySession, load_query
            with ReadOnlySession(uri) as sess:
                rows = sess.execute(load_query('auth_get_active_users'))
            from app.services import practitioner_names
            practitioner_names.swap(rows, 'UserId', 'Name')
            local_admins = User.query.filter_by(is_local_admin=True, is_active=True).all()
            return ([{'name': u.display_name or u.username, 'value': u.username} for u in local_admins]
                    + [{'name': r['Name'], 'value': str(r['UserId'])} for r in rows])
        except Exception as e:
            current_app.logger.warning(
                'Login user list: BPSDB unavailable (%s), using cached users', e)
            users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
            return [{'name': u.display_name, 'value': u.username} for u in users]

    @staticmethod
    def authenticate(username: str, password: str) -> User | None:
        """Route authentication: local admin → werkzeug hash; everyone else → BPSDB live."""
        if not username or not password:
            return None
        key = username.strip()

        # Local admin path first — explicit flag, werkzeug hash, no BPSDB involved
        local = User.query.filter_by(username=key, is_local_admin=True, is_active=True).first()
        if local:
            return local if local.check_password(password) else None

        # BPSDB path — submitted value must be a numeric UserId
        if not key.isdigit():
            return None
        return AuthService._authenticate_bpsdb(int(key), password)

    @staticmethod
    def _authenticate_bpsdb(userid: int, password: str) -> User | None:
        """Verify against BPSDB using SHA256(password + salt), then sync shadow account."""
        from app.sql.query_loader import ReadOnlySession, load_query

        uri = current_app.config.get('BPSDB_URI')
        if not uri:
            current_app.logger.error('BPSDB_URI not configured — cannot authenticate')
            return None

        try:
            with ReadOnlySession(uri) as sess:
                rows = sess.execute(load_query('auth_get_user_by_id'), [userid])
        except Exception as e:
            current_app.logger.error('BPSDB auth connection failed: %s', e)
            return None

        if not rows:
            return None

        record = rows[0]
        # The login list offers only these groups; refuse the rest here too,
        # so a user number sent directly can't get round it.
        if record.get('GroupCode') not in LOGIN_GROUP_LEVELS:
            current_app.logger.info('BPSDB user %d refused: group %s may not log in',
                                    userid, record.get('GroupCode'))
            return None
        stored_hash = (record.get('Password') or '').strip().upper()
        salt = str(record.get('PasswordSalt') or '')

        if not salt or not stored_hash:
            current_app.logger.warning('BPSDB user %d has no password/salt', userid)
            return None

        alg = hashlib.sha256()
        alg.update(password.encode())
        alg.update(salt.encode())
        computed = alg.hexdigest().upper()

        if not hmac.compare_digest(computed, stored_hash):
            return None

        return AuthService._sync_shadow(userid, record)

    @staticmethod
    def _sync_shadow(userid: int, bps: dict) -> User:
        """Create or update the Gen5 shadow account for a verified BPSDB user."""
        user = User.query.filter_by(bpsdb_user_id=userid).first()
        if not user:
            user = User.query.filter_by(username=str(userid)).first()
        if not user:
            user = User(username=str(userid), password_hash='BPSDB_AUTH', is_local_admin=False)
            db.session.add(user)

        title      = (bps.get('Title') or '').strip()
        firstname  = (bps.get('Firstname') or '').strip()
        surname    = (bps.get('Surname') or '').strip()
        group_code = bps.get('GroupCode')
        provider   = (bps.get('ProviderNo')   or '').strip()
        prescriber = (bps.get('PrescriberNo') or '').strip()

        user.bpsdb_user_id       = userid
        user.bpsdb_provider_no   = provider   or None
        user.bpsdb_prescriber_no = prescriber or None
        user.bp_display_name     = ' '.join(filter(None, [title, firstname, surname])) or str(userid)
        user.display_name        = user.preferred_name or user.bp_display_name   # ADR-106
        user.security_level      = LOGIN_GROUP_LEVELS.get(group_code, 1)
        user.is_active           = True
        db.session.commit()
        return user

    @staticmethod
    def record_login(user: User) -> None:
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()
        current_app.logger.info('Login: %s (level %d)', user.display_name, user.security_level)
