import enum
from datetime import datetime, timezone
from app.extensions import db


class MappingTable(db.Model):
    """Registry entry for an admin-managed mapping/lookup table.

    Each row corresponds to a physical PostgreSQL table named mapdata_{name}.
    Physical tables are created/dropped via MappingService DDL calls.
    """
    __tablename__ = 'mapping_tables'

    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(40), unique=True, nullable=False)
    label             = db.Column(db.String(200), nullable=False)
    description       = db.Column(db.Text, nullable=True)
    refresh_url       = db.Column(db.String(500), nullable=True)
    cache_ttl_seconds = db.Column(db.Integer, nullable=True)
    last_refreshed_at = db.Column(db.DateTime, nullable=True)
    row_count         = db.Column(db.Integer, nullable=False, default=0)
    created_at        = db.Column(db.DateTime, nullable=False,
                                  default=lambda: datetime.now(timezone.utc))
    updated_at        = db.Column(db.DateTime, nullable=False,
                                  default=lambda: datetime.now(timezone.utc),
                                  onupdate=lambda: datetime.now(timezone.utc))

    @property
    def physical_table(self) -> str:
        return f'mapdata_{self.name}'

    @property
    def is_stale(self) -> bool:
        if not self.cache_ttl_seconds or not self.last_refreshed_at:
            return False
        age = (datetime.now(timezone.utc) - self.last_refreshed_at.replace(tzinfo=timezone.utc)).total_seconds()
        return age > self.cache_ttl_seconds

    @property
    def freshness_label(self) -> str | None:
        """Human-readable age string, or None if no refresh has occurred."""
        if not self.last_refreshed_at:
            return None
        age = (datetime.now(timezone.utc) - self.last_refreshed_at.replace(tzinfo=timezone.utc)).total_seconds()
        if age < 120:
            return f'{int(age)}s ago'
        if age < 3600:
            return f'{int(age // 60)}m ago'
        if age < 86400:
            return f'{int(age // 3600)}h ago'
        return f'{int(age // 86400)}d ago'

    def __repr__(self) -> str:
        return f'<MappingTable {self.name}>'
