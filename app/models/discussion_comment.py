from datetime import datetime

from app.extensions import db


class DiscussionComment(db.Model):
    __tablename__ = "discussion_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("discussion_posts.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    author_label = db.Column(db.String(80), nullable=False)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    post = db.relationship("DiscussionPost", back_populates="comments")

    @property
    def score(self):
        return (self.upvotes or 0) - (self.downvotes or 0)

    def __repr__(self):
        return f"<DiscussionComment {self.id}>"
