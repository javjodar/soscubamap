import json
from flask import render_template, redirect, url_for, flash
from flask_login import login_required

from app.extensions import db
from app.models.post import Post
from app.models.category import Category
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.media import Media
from app.services.media_upload import media_json_from_post, parse_media_json
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
        repressor_name=post.repressor_name,
        other_type=post.other_type,
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
    post.repressor_name = edit.repressor_name
    post.other_type = edit.other_type
    if edit.category_id:
        post.category_id = edit.category_id
    post.polygon_geojson = edit.polygon_geojson
    post.links_json = edit.links_json
    if edit.media_json:
        media_items = parse_media_json(edit.media_json)
        Media.query.filter_by(post_id=post.id).delete()
        for item in media_items:
            db.session.add(
                Media(
                    post_id=post.id,
                    file_url=item.get("url"),
                    caption=(item.get("caption") or None),
                )
            )

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


@moderation_bp.route("/ediciones/<int:edit_id>")
@login_required
@role_required("moderador", "administrador")
def edit_detail(edit_id):
    edit = PostEditRequest.query.get_or_404(edit_id)
    post = Post.query.get_or_404(edit.post_id)
    edit_category = None
    if edit.category_id:
        edit_category = Category.query.get(edit.category_id)
    links = []
    if edit.links_json:
        try:
            links = json.loads(edit.links_json)
        except Exception:
            links = []
    media_items = []
    if edit.media_json:
        media_items = parse_media_json(edit.media_json)
    return render_template(
        "moderation/edit_detail.html",
        edit=edit,
        post=post,
        edit_category=edit_category,
        links=links,
        media_items=media_items,
    )
