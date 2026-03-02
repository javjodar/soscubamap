from flask import render_template, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models.post import Post
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.media import Media
from app.services.media_upload import media_json_from_post
import json
from app.services.authz import role_required
from . import moderation_bp


@moderation_bp.route("/")
@login_required
@role_required("moderador", "administrador")
def dashboard():
    pending = Post.query.filter_by(status="pending").order_by(Post.created_at.desc()).all()
    pending_edits = PostEditRequest.query.filter_by(status="pending").order_by(PostEditRequest.created_at.desc()).all()
    return render_template("moderation/dashboard.html", pending=pending, pending_edits=pending_edits)


@moderation_bp.route("/aprobar/<int:post_id>", methods=["POST"])
@login_required
@role_required("moderador", "administrador")
def approve(post_id):
    post = Post.query.get_or_404(post_id)
    post.status = "approved"
    db.session.commit()
    flash("Reporte aprobado.", "success")
    return redirect(url_for("moderation.dashboard"))


@moderation_bp.route("/rechazar/<int:post_id>", methods=["POST"])
@login_required
@role_required("moderador", "administrador")
def reject(post_id):
    post = Post.query.get_or_404(post_id)
    post.status = "rejected"
    db.session.commit()
    flash("Reporte rechazado.", "success")
    return redirect(url_for("moderation.dashboard"))


@moderation_bp.route("/ediciones/<int:edit_id>/aprobar", methods=["POST"])
@login_required
@role_required("moderador", "administrador")
def approve_edit(edit_id):
    edit = PostEditRequest.query.get_or_404(edit_id)
    post = Post.query.get_or_404(edit.post_id)

    revision = PostRevision(
        post_id=post.id,
        editor_id=edit.editor_id,
        editor_label=edit.editor_label,
        reason=edit.reason,
        title=post.title,
        description=post.description,
        latitude=post.latitude,
        longitude=post.longitude,
        address=post.address,
        province=post.province,
        municipality=post.municipality,
        category_id=post.category_id,
        polygon_geojson=post.polygon_geojson,
        links_json=post.links_json,
        media_json=media_json_from_post(post),
    )
    db.session.add(revision)

    post.title = edit.title
    post.description = edit.description
    post.latitude = edit.latitude
    post.longitude = edit.longitude
    post.address = edit.address
    post.province = edit.province
    post.municipality = edit.municipality
    if edit.category_id:
        post.category_id = edit.category_id
    post.polygon_geojson = edit.polygon_geojson
    post.links_json = edit.links_json
    if edit.media_json:
        try:
            media_urls = json.loads(edit.media_json) or []
        except Exception:
            media_urls = []
        Media.query.filter_by(post_id=post.id).delete()
        for url in media_urls:
            db.session.add(Media(post_id=post.id, file_url=url))

    edit.status = "approved"
    db.session.commit()
    flash("Edición aprobada.", "success")
    return redirect(url_for("moderation.dashboard"))


@moderation_bp.route("/ediciones/<int:edit_id>/rechazar", methods=["POST"])
@login_required
@role_required("moderador", "administrador")
def reject_edit(edit_id):
    edit = PostEditRequest.query.get_or_404(edit_id)
    edit.status = "rejected"
    db.session.commit()
    flash("Edición rechazada.", "success")
    return redirect(url_for("moderation.dashboard"))
