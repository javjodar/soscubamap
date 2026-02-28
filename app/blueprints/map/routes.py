from decimal import Decimal
import secrets
from flask import render_template, current_app, redirect, url_for, request, flash
from flask_login import current_user

from app.models.category import Category
from app.models.post import Post
from app.models.user import User
from app.models.role import Role
from app.models.site_setting import SiteSetting
from app.extensions import db
from . import map_bp


@map_bp.route("/")
def dashboard():
    categories = Category.query.order_by(Category.id.asc()).all()
    posts = Post.query.filter_by(status="approved").all()
    return render_template(
        "map/dashboard.html",
        categories=categories,
        posts=posts,
        google_maps_api_key=current_app.config.get("GOOGLE_MAPS_API_KEY"),
    )


@map_bp.route("/nuevo", methods=["GET", "POST"])
def new_post():
    categories = Category.query.order_by(Category.id.asc()).all()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category_id = request.form.get("category_id")
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()
        address = request.form.get("address", "").strip()
        polygon_geojson = request.form.get("polygon_geojson", "").strip()

        if not title or not description or not category_id or not latitude or not longitude:
            flash("Completa todos los campos obligatorios.", "error")
            return redirect(url_for("map.new_post"))

        try:
            lat = Decimal(latitude)
            lng = Decimal(longitude)
        except Exception:
            flash("Latitud/longitud invalidas.", "error")
            return redirect(url_for("map.new_post"))

        author_id = None
        if current_user.is_authenticated:
            author_id = current_user.id
        else:
            # Create a one-off anonymous user for this report
            anon_user = User(email=f"anon+{secrets.token_hex(6)}@local")
            anon_user.set_password(secrets.token_urlsafe(16))
            anon_user.ensure_anon_code()
            default_role = Role.query.filter_by(name="colaborador").first()
            if default_role:
                anon_user.roles.append(default_role)
            db.session.add(anon_user)
            db.session.flush()
            author_id = anon_user.id

        moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
        moderation_enabled = True
        if moderation_setting:
            moderation_enabled = moderation_setting.value == "true"

        post = Post(
            title=title,
            description=description,
            category_id=int(category_id),
            latitude=lat,
            longitude=lng,
            address=address or None,
            polygon_geojson=polygon_geojson or None,
            author_id=author_id,
        )
        post.status = "pending" if moderation_enabled else "approved"
        db.session.add(post)
        db.session.commit()

        if moderation_enabled:
            flash("Reporte enviado a moderacion.", "success")
        else:
            flash("Reporte publicado.", "success")
        return redirect(url_for("map.dashboard"))

    preset_lat = request.args.get("lat", "")
    preset_lng = request.args.get("lng", "")
    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"

    return render_template(
        "map/new_post.html",
        categories=categories,
        preset_lat=preset_lat,
        preset_lng=preset_lng,
        moderation_enabled=moderation_enabled,
    )


@map_bp.route("/donar")
def donate():
    return render_template("map/donate.html")
