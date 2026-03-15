from datetime import datetime

from app.extensions import db


class ConnectivitySnapshot(db.Model):
    __tablename__ = "connectivity_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    ingestion_run_id = db.Column(
        db.Integer,
        db.ForeignKey("connectivity_ingestion_runs.id", ondelete="SET NULL"),
        index=True,
    )
    observed_at_utc = db.Column(db.DateTime, nullable=False, index=True)
    fetched_at_utc = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    traffic_value = db.Column(db.Float, nullable=False)
    baseline_value = db.Column(db.Float)
    score = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(24), nullable=False, index=True)
    is_partial = db.Column(db.Boolean, nullable=False, default=False)
    confidence = db.Column(db.String(32), nullable=False, default="country_level")
    method = db.Column(db.String(64), nullable=False, default="national_replication_v1")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    ingestion_run = db.relationship("ConnectivityIngestionRun", back_populates="snapshots")
    provinces = db.relationship(
        "ConnectivityProvinceStatus",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return (
            f"<ConnectivitySnapshot {self.id} {self.observed_at_utc.isoformat()} "
            f"{self.status} {self.score:.1f}>"
        )
