from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from app.services.authz import role_required
from app.services.settings import get_setting, set_setting
from app.models.post import Post
from app.models.discussion_post import DiscussionPost
from app.models.discussion_comment import DiscussionComment
from app.models.discussion_tag import DiscussionTag
from app.models.location_report import LocationReport
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.category import Category
from app.extensions import db
from app.models.media import Media
from app.services.media_upload import media_json_from_post, parse_media_json, get_media_payload
from app.services.input_safety import has_malicious_input
from app.services.geo_lookup import lookup_location, list_provinces, municipalities_map
from flask_login import current_user
import json
from decimal import Decimal
from sqlalchemy import func
from app.services.markdown_utils import render_markdown
from app.services.discussion_tags import upsert_tags
from . import admin_bp


def _resolve_geo_location(lat, lng, province, municipality):
    try:
        auto_prov, auto_mun = lookup_location(lat, lng)
    except Exception:
        return province, municipality
    if auto_prov:
        province = auto_prov
    if auto_mun:
        municipality = auto_mun
    return province, municipality


@admin_bp.route("/")
@login_required
@role_required("administrador")
def dashboard():
    moderation_enabled = get_setting("moderation_enabled", "true") == "true"
    location_reports = (
        LocationReport.query.order_by(LocationReport.created_at.desc())
        .limit(10)
        .all()
    )
    return render_template(
        "admin/dashboard.html",
        moderation_enabled=moderation_enabled,
        location_reports=location_reports,
    )


@admin_bp.route("/moderacion", methods=["POST"])
@login_required
@role_required("administrador")
def toggle_moderation():
    enabled = request.form.get("moderation_enabled") == "on"
    set_setting("moderation_enabled", "true" if enabled else "false")
    flash("Moderación actualizada.", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/reportes")
@login_required
@role_required("administrador")
def reports():
    status = request.args.get("status", "approved")
    query = Post.query
    if status == "all":
        posts = query.order_by(Post.created_at.desc()).all()
    else:
        posts = query.filter_by(status=status).order_by(Post.created_at.desc()).all()
    return render_template("admin/reports.html", posts=posts, status=status)


@admin_bp.route("/reportes-ubicacion")
@login_required
@role_required("administrador")
def location_reports():
    reports = LocationReport.query.order_by(LocationReport.created_at.desc()).all()
    return render_template("admin/location_reports.html", reports=reports)


@admin_bp.route("/discusiones")
@login_required
@role_required("administrador")
def discussions():
    posts = DiscussionPost.query.order_by(DiscussionPost.created_at.desc()).all()
    counts = dict(
        db.session.query(DiscussionComment.post_id, func.count(DiscussionComment.id))
        .group_by(DiscussionComment.post_id)
        .all()
    )
    return render_template("admin/discussions.html", posts=posts, comment_counts=counts)


@admin_bp.route("/discusiones/<int:post_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def edit_discussion(post_id):
    post = DiscussionPost.query.get_or_404(post_id)
    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        links_list = request.form.getlist("links[]")
        links_list = [link.strip() for link in links_list if link.strip()]
        selected_tags = request.form.getlist("tags[]")
        new_tags = request.form.get("new_tags", "")
        new_tags = [t.strip() for t in new_tags.split(",") if t.strip()]

        if not title or not body:
            flash("Título y contenido son obligatorios.", "error")
            return redirect(url_for("admin.edit_discussion", post_id=post.id))

        post.title = title
        post.body = body
        post.body_html = render_markdown(body)
        post.links_json = json.dumps(links_list) if links_list else None
        post.tags = upsert_tags(selected_tags + new_tags)
        db.session.commit()
        flash("Discusión actualizada.", "success")
        return redirect(url_for("admin.discussions"))

    images = parse_media_json(post.images_json)
    tags = DiscussionTag.query.order_by(DiscussionTag.name.asc()).all()
    return render_template(
        "admin/edit_discussion.html",
        post=post,
        links=links,
        images=images,
        tags=tags,
    )


@admin_bp.route("/discusiones/<int:post_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def delete_discussion(post_id):
    post = DiscussionPost.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("Discusión eliminada.", "success")
    return redirect(url_for("admin.discussions"))


@admin_bp.route("/discusiones/comentarios/<int:comment_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def delete_discussion_comment(comment_id):
    comment = DiscussionComment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash("Comentario eliminado.", "success")
    return redirect(request.referrer or url_for("admin.discussions"))


@admin_bp.route("/reportes/<int:post_id>/estado", methods=["POST"])
@login_required
@role_required("administrador")
def update_report_status(post_id):
    status = request.form.get("status")
    if status not in {"approved", "hidden", "deleted", "rejected", "pending"}:
        flash("Estado inválido.", "error")
        return redirect(url_for("admin.reports"))

    post = Post.query.get_or_404(post_id)
    post.status = status
    db.session.commit()
    flash("Reporte actualizado.", "success")
    return redirect(url_for("admin.reports", status=request.args.get("status", "approved")))


@admin_bp.route("/reportes/bulk-delete", methods=["POST"])
@login_required
@role_required("administrador")
def bulk_delete_reports():
    ids = request.form.getlist("selected_ids")
    status = request.args.get("status", "approved")
    if not ids:
        flash("Selecciona al menos un reporte.", "error")
        return redirect(url_for("admin.reports", status=status))

    try:
        id_list = [int(i) for i in ids]
    except Exception:
        flash("Selección inválida.", "error")
        return redirect(url_for("admin.reports", status=status))

    posts = Post.query.filter(Post.id.in_(id_list)).all()
    for post in posts:
        post.status = "deleted"
    db.session.commit()
    flash(f"Reportes eliminados: {len(posts)}.", "success")
    return redirect(url_for("admin.reports", status=status))


@admin_bp.route("/reportes/<int:post_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def edit_report(post_id):
    post = Post.query.get_or_404(post_id)
    categories = Category.query.order_by(Category.id.asc()).all()
    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        edit_reason = request.form.get("edit_reason", "").strip()
        category_id = request.form.get("category_id")
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()
        address = request.form.get("address", "").strip()
        province = request.form.get("province", "").strip()
        municipality = request.form.get("municipality", "").strip()
        repressor_name = request.form.get("repressor_name", "").strip()
        other_type = request.form.get("other_type", "").strip()
        polygon_geojson = request.form.get("polygon_geojson", "").strip()
        links_list = request.form.getlist("links[]")
        links_list = [link.strip() for link in links_list if link.strip()]

        if has_malicious_input([title, description, edit_reason, address, province, municipality, repressor_name, other_type] + links_list):
            flash("Se detectó contenido sospechoso. Revisa y vuelve a intentar.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))

        if not title or not description or not category_id or not latitude or not longitude:
            flash("Completa todos los campos obligatorios.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))
        if len(description) < 50:
            flash("La descripción debe tener al menos 50 caracteres.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))
        if not edit_reason:
            flash("El motivo de edición es obligatorio.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))

        try:
            lat = Decimal(latitude)
            lng = Decimal(longitude)
        except Exception:
            flash("Latitud/longitud inválidas.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))

        province, municipality = _resolve_geo_location(lat, lng, province, municipality)
        if not province or not municipality:
            flash("Provincia y municipio son obligatorios.", "error")
            return redirect(url_for("admin.edit_report", post_id=post.id))

        category = Category.query.get(int(category_id)) if category_id else None
        slug = category.slug if category else ""
        existing_media_count = len(get_media_payload(post))
        if slug == "residencia-represor":
            if not repressor_name:
                flash("Debes indicar el nombre o apodo del represor.", "error")
                return redirect(url_for("admin.edit_report", post_id=post.id))
            if existing_media_count < 1:
                flash("Debes subir al menos una imagen del represor.", "error")
                return redirect(url_for("admin.edit_report", post_id=post.id))
        if slug == "otros":
            if not other_type:
                flash("Debes especificar el tipo en la categoría Otros.", "error")
                return redirect(url_for("admin.edit_report", post_id=post.id))

        moderation_enabled = get_setting("moderation_enabled", "true") == "true"

        editor_label = "Admin"
        if current_user.is_authenticated:
            if current_user.anon_code:
                editor_label = f"Anon-{current_user.anon_code}"
            else:
                editor_label = current_user.email

        if moderation_enabled:
            edit_req = PostEditRequest(
                post_id=post.id,
                editor_id=current_user.id if current_user.is_authenticated else None,
                editor_label=editor_label,
                reason=edit_reason,
                title=title,
                description=description,
                latitude=lat,
                longitude=lng,
                address=address or None,
                province=province or None,
                municipality=municipality or None,
                repressor_name=repressor_name or None,
                other_type=other_type or None,
                category_id=int(category_id),
                polygon_geojson=polygon_geojson or None,
                links_json=json.dumps(links_list) if links_list else None,
            )
            db.session.add(edit_req)
            db.session.commit()
            flash("Edición enviada a moderación.", "success")
            return redirect(url_for("admin.edit_report", post_id=post.id))

        # Guardar revisión previa
        revision = PostRevision(
            post_id=post.id,
            editor_id=current_user.id if current_user.is_authenticated else None,
            editor_label=editor_label,
            reason=edit_reason,
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

        post.title = title
        post.description = description
        post.category_id = int(category_id)
        post.latitude = lat
        post.longitude = lng
        post.address = address or None
        post.province = province or None
        post.municipality = municipality or None
        post.repressor_name = repressor_name or None
        post.other_type = other_type or None
        post.polygon_geojson = polygon_geojson or None
        post.links_json = json.dumps(links_list) if links_list else None
        db.session.commit()

        flash("Reporte actualizado.", "success")
        return redirect(url_for("admin.edit_report", post_id=post.id))

    return render_template(
        "admin/edit_report.html",
        post=post,
        categories=categories,
        links=links,
        media_items=get_media_payload(post),
        provinces=list_provinces(),
        municipalities_map=municipalities_map(),
    )


@admin_bp.route("/reportes/<int:post_id>/revisiones/<int:revision_id>/restaurar", methods=["POST"])
@login_required
@role_required("administrador")
def restore_revision(post_id, revision_id):
    post = Post.query.get_or_404(post_id)
    revision = PostRevision.query.get_or_404(revision_id)
    if revision.post_id != post.id:
        flash("Revisión inválida.", "error")
        return redirect(url_for("map.post_history", post_id=post.id))

    # Guardar snapshot actual antes de restaurar
    editor_label = current_user.email if current_user.is_authenticated else "Admin"
    snapshot = PostRevision(
        post_id=post.id,
        editor_id=current_user.id if current_user.is_authenticated else None,
        editor_label=editor_label,
        reason="Restauración de versión anterior",
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
    db.session.add(snapshot)

    post.title = revision.title
    post.description = revision.description
    post.latitude = revision.latitude
    post.longitude = revision.longitude
    post.address = revision.address
    post.province = revision.province
    post.municipality = revision.municipality
    if revision.category_id:
        post.category_id = revision.category_id
    post.polygon_geojson = revision.polygon_geojson
    post.links_json = revision.links_json
    if revision.media_json:
        media_items = parse_media_json(revision.media_json)
        Media.query.filter_by(post_id=post.id).delete()
        for item in media_items:
            db.session.add(
                Media(
                    post_id=post.id,
                    file_url=item.get("url"),
                    caption=(item.get("caption") or None),
                )
            )
    db.session.commit()

    flash("Reporte restaurado a una versión anterior.", "success")
    return redirect(url_for("map.post_history", post_id=post.id))
