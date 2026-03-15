from datetime import datetime

from app.extensions import db


class ConnectivityProvinceStatus(db.Model):
    __tablename__ = "connectivity_province_statuses"

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey("connectivity_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    province = db.Column(db.String(120), nullable=False, index=True)
    score = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(24), nullable=False, index=True)
    confidence = db.Column(db.String(32), nullable=False, default="estimated_country_level")
    method = db.Column(db.String(64), nullable=False, default="national_replication_v1")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    snapshot = db.relationship("ConnectivitySnapshot", back_populates="provinces")

    __table_args__ = (
        db.UniqueConstraint("snapshot_id", "province", name="uq_connectivity_snapshot_province"),
    )

    def __repr__(self):
        return (
            f"<ConnectivityProvinceStatus snapshot={self.snapshot_id} "
            f"province={self.province} status={self.status}>"
        )
