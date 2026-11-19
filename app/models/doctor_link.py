from datetime import datetime
from app.extensions import db


class DoctorLink(db.Model):
    __tablename__ = 'doctor_links'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    name       = db.Column(db.String(200), nullable=False)
    url        = db.Column(db.String(2000), nullable=False)
    keywords   = db.Column(db.String(500), nullable=True)
    popularity = db.Column(db.Integer, default=0, nullable=False)
    dead_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def favicon_url(self) -> str:
        try:
            from urllib.parse import urlparse
            domain = urlparse(self.url).netloc or self.url
            return f'https://www.google.com/s2/favicons?domain={domain}&sz=32'
        except Exception:
            return ''

    def __repr__(self) -> str:
        return f'<DoctorLink {self.id} {self.name!r}>'
