from datetime import datetime

from app.extensions import db


class VoteRecord(db.Model):
    __tablename__ = "vote_records"

    id = db.Column(db.Integer, primary_key=True)
    target_type = db.Column(db.String(32), nullable=False, index=True)
    target_id = db.Column(db.Integer, nullable=False, index=True)
    voter_hash = db.Column(db.String(64), nullable=False, index=True)
    value = db.Column(db.SmallInteger, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("target_type", "target_id", "voter_hash", name="uq_vote_record"),
    )

    def __repr__(self) -> str:
        return f"<VoteRecord {self.target_type}:{self.target_id} {self.value}>"
