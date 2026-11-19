from app.extensions import db


class DataBundle(db.Model):
    __tablename__ = 'data_bundles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    blocks = db.relationship('BundleBlock', backref='bundle', lazy='dynamic',
                             order_by='BundleBlock.block_order',
                             cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<DataBundle {self.name}>'


class BundleBlock(db.Model):
    __tablename__ = 'bundle_blocks'

    id = db.Column(db.Integer, primary_key=True)
    bundle_id = db.Column(db.Integer, db.ForeignKey('data_bundles.id'), nullable=False)
    block_order = db.Column(db.Integer, nullable=False, default=0)
    # Atomic BP data block name
    block_source = db.Column(db.String(200), nullable=False)
    label = db.Column(db.String(200))
    config_json = db.Column(db.Text, nullable=False, default='{}')

    def __repr__(self) -> str:
        return f'<BundleBlock {self.block_source} #{self.block_order}>'
