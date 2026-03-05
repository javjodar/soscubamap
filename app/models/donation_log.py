from datetime import datetime

from app.extensions import db


class DonationLog(db.Model):
    __tablename__ = "donation_logs"

    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.String(64), nullable=False)
    method = db.Column(db.String(120), nullable=False)
    donated_at = db.Column(db.Date, nullable=False)
    destination = db.Column(db.String(160), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<DonationLog {self.id} {self.amount} {self.method}>"
