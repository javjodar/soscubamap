from datetime import datetime
from sqlalchemy import Enum

from app.extensions import db


post_status_enum = Enum(
    "pending",
    "approved",
    "rejected",
    name="post_status",
)


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=False)
    longitude = db.Column(db.Numeric(9, 6), nullable=False)
    address = db.Column(db.String(255))
    polygon_geojson = db.Column(db.Text)

    status = db.Column(post_status_enum, default="pending", nullable=False)
    is_anonymous = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)

    author = db.relationship("User", back_populates="posts")
    category = db.relationship("Category", back_populates="posts")
    media = db.relationship("Media", back_populates="post", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Post {self.id} {self.title}>"
