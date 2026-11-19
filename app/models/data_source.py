from datetime import datetime, timezone

from app.extensions import db


# location_type values
LOCATION_HTTP      = 'http_url'
LOCATION_LOCAL     = 'local_file'
LOCATION_NETWORK   = 'network_path'
LOCATION_BPSDB     = 'bpsdb_query'

LOCATION_TYPES = {
    LOCATION_HTTP:    'HTTP URL',
    LOCATION_LOCAL:   'Local File',
    LOCATION_NETWORK: 'Network Path',
    LOCATION_BPSDB:   'BPSDB Query',
}


class DataSource(db.Model):
    """Registry of data feed locations for visualisation pages."""
    __tablename__ = 'data_sources'

    id               = db.Column(db.Integer,     primary_key=True)
    key              = db.Column(db.String(40),  unique=True, nullable=False, index=True)
    display_name     = db.Column(db.String(120), nullable=False)
    description      = db.Column(db.Text)
    location         = db.Column(db.String(500), nullable=False)
    location_type    = db.Column(db.String(40),  nullable=False, default=LOCATION_HTTP, index=True)
    source_type      = db.Column(db.String(40),  nullable=False, index=True)
    chart_config_json = db.Column(db.Text)
    show_in_topnav   = db.Column(db.Boolean,     nullable=False, default=False)
    is_active        = db.Column(db.Boolean,     nullable=False, default=True)
    created_at       = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))

    @property
    def location_type_label(self) -> str:
        return LOCATION_TYPES.get(self.location_type, self.location_type)

    def __repr__(self) -> str:
        return f'<DataSource {self.key}>'
