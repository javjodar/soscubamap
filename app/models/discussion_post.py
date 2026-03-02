from datetime import datetime

from app.extensions import db


class DiscussionPost(db.Model):
    __tablename__ = "discussion_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    links_json = db.Column(db.Text)
    images_json = db.Column(db.Text)
    author_label = db.Column(db.String(80), nullable=False)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    comments = db.relationship(
        "DiscussionComment",
        back_populates="post",
        cascade="all, delete-orphan",
    )

    @property
    def score(self):
        return (self.upvotes or 0) - (self.downvotes or 0)

    def __repr__(self):
        return f"<DiscussionPost {self.id} {self.title}>"
