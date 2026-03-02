from datetime import datetime
from app.extensions import db


class PostRevision(db.Model):
    __tablename__ = "post_revisions"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    editor_label = db.Column(db.String(60))
    reason = db.Column(db.Text)

    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    latitude = db.Column(db.Numeric(9, 6), nullable=False)
    longitude = db.Column(db.Numeric(9, 6), nullable=False)
    address = db.Column(db.String(255))
    province = db.Column(db.String(120))
    municipality = db.Column(db.String(120))
    category_id = db.Column(db.Integer)
    polygon_geojson = db.Column(db.Text)
    links_json = db.Column(db.Text)
    media_json = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    post = db.relationship("Post", backref="revisions")
    editor = db.relationship("User")

    def __repr__(self):
        return f"<PostRevision {self.id} post={self.post_id}>"
