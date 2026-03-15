from datetime import datetime

from app.extensions import db


class ConnectivityIngestionRun(db.Model):
    __tablename__ = "connectivity_ingestion_runs"

    id = db.Column(db.Integer, primary_key=True)
    scheduled_for_utc = db.Column(db.DateTime, index=True)
    started_at_utc = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    finished_at_utc = db.Column(db.DateTime)
    status = db.Column(db.String(24), nullable=False, default="running", index=True)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    api_url = db.Column(db.String(1000))
    error_message = db.Column(db.Text)
    payload_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    snapshots = db.relationship(
        "ConnectivitySnapshot",
        back_populates="ingestion_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<ConnectivityIngestionRun {self.id} {self.status}>"
