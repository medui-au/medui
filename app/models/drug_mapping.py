from datetime import datetime, timezone
from app.extensions import db


class DrugMapping(db.Model):
    __tablename__ = 'drug_mappings'

    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, unique=True, nullable=False, index=True)
    brand_name     = db.Column(db.String(200), nullable=False)
    generic_name   = db.Column(db.String(200), nullable=False)
    atc_code       = db.Column(db.String(20), nullable=True)
    approved       = db.Column(db.Boolean, nullable=False, default=False,
                               server_default='false')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at    = db.Column(db.DateTime, nullable=True)
    source         = db.Column(db.String(40), nullable=False, default='manual')
    created_at     = db.Column(db.DateTime, nullable=False,
                               default=lambda: datetime.now(timezone.utc))

    approved_by = db.relationship('User', foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return f'<DrugMapping {self.product_id} {self.brand_name!r}>'
