from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


# Lowest security level that may start AI queries (User.can_use_ai).
AI_LEVEL = 5


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))   # the name MedUI shows: preferred_name, else the BP name
    # ADR-106: the name the user goes by, set in My Settings or Setup → Users; login never
    # changes it. bp_display_name is the name from BP, refreshed at each login.
    preferred_name  = db.Column(db.String(120))
    bp_display_name = db.Column(db.String(120))
    email = db.Column(db.String(200))

    # 1-9: 9 = full admin, 5+ = AI (doctors), 3 = nurse, 2 = reception, 1 = read-only.
    # BP users get theirs from their group at every login (auth_service).
    security_level = db.Column(db.Integer, nullable=False, default=1)
    is_local_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # BPSDB shadow fields (for linking to EHR provider records)
    bpsdb_provider_id    = db.Column(db.Integer)
    bpsdb_user_id        = db.Column(db.Integer)
    bpsdb_internal_id    = db.Column(db.Integer)  # staff member's own BPS patient_id
    bpsdb_provider_no    = db.Column(db.String(20))  # Medicare provider number e.g. "0497452W"
    bpsdb_prescriber_no  = db.Column(db.String(20))  # PBS prescriber number (numeric)
    title                = db.Column(db.String(20))   # Honorific for formal output e.g. "Dr."

    theme = db.Column(db.String(40), default='light')
    email_signature = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = db.Column(db.DateTime)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_level(self, level: int) -> bool:
        return self.security_level >= level

    @property
    def can_use_ai(self) -> bool:
        """May start AI queries: doctors (level 5+) and administrators."""
        return bool(self.is_admin or self.security_level >= AI_LEVEL)

    @property
    def is_admin(self) -> bool:
        """True for local admin accounts and BPSDB users at security level 9."""
        return bool(self.is_local_admin or self.security_level >= 9)

    def __repr__(self) -> str:
        return f'<User {self.username} L{self.security_level}>'
