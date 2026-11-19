from datetime import datetime
from app.extensions import db


class SQLQuery(db.Model):
    __tablename__ = 'sql_queries'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(200), unique=True, nullable=False)
    # 'bpsdb' = SQL Server via ReadOnlySession; 'postgres' = Gen5 PostgreSQL
    database_target = db.Column(db.String(20), nullable=False, default='bpsdb')
    sql_text        = db.Column(db.Text, nullable=False, default='SELECT ')
    description     = db.Column(db.Text)

    # App-available query flag (PatientJSON bundle context)
    is_app_enabled  = db.Column(db.Boolean, nullable=False, default=False)
    # Max rows returned when used as a PatientJSON block (safety constraint)
    app_row_limit   = db.Column(db.Integer, nullable=False, default=200)

    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f'<SQLQuery {self.name}>'
