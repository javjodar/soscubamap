from flask import render_template, redirect, url_for, request, flash
from flask_login import login_required

from app.services.authz import role_required
from app.services.settings import get_setting, set_setting
from app.models.post import Post
from app.extensions import db
from . import admin_bp


@admin_bp.route("/")
@login_required
@role_required("administrador")
def dashboard():
    moderation_enabled = get_setting("moderation_enabled", "true") == "true"
    return render_template("admin/dashboard.html", moderation_enabled=moderation_enabled)


@admin_bp.route("/moderacion", methods=["POST"])
@login_required
@role_required("administrador")
def toggle_moderation():
    enabled = request.form.get("moderation_enabled") == "on"
    set_setting("moderation_enabled", "true" if enabled else "false")
    flash("Moderacion actualizada.", "success")
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


@admin_bp.route("/reportes/<int:post_id>/estado", methods=["POST"])
@login_required
@role_required("administrador")
def update_report_status(post_id):
    status = request.form.get("status")
    if status not in {"approved", "hidden", "deleted", "rejected", "pending"}:
        flash("Estado invalido.", "error")
        return redirect(url_for("admin.reports"))

    post = Post.query.get_or_404(post_id)
    post.status = status
    db.session.commit()
    flash("Reporte actualizado.", "success")
    return redirect(url_for("admin.reports", status=request.args.get("status", "approved")))
