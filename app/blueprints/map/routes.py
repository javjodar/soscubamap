import csv
import html
import io
import json
import secrets
import textwrap
from datetime import datetime
from decimal import Decimal

from flask import (
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user
from sqlalchemy.orm import selectinload

from app.extensions import db, limiter
from app.models.category import Category
from app.models.donation_log import DonationLog
from app.models.location_report import LocationReport
from app.models.media import Media
from app.models.post import Post
from app.models.post_edit_request import PostEditRequest
from app.models.post_revision import PostRevision
from app.models.role import Role
from app.models.site_setting import SiteSetting
from app.models.user import User
from app.models.vote_record import VoteRecord
from app.services.category_rules import is_other_type_allowed
from app.services.category_sort import sort_categories_for_forms
from app.services.content_quality import validate_description, validate_title
from app.services.geo_lookup import (
    is_within_cuba_bounds,
    list_municipalities,
    list_provinces,
    lookup_location,
    municipalities_map,
)
from app.services.input_safety import has_malicious_input
from app.services.media_upload import (
    get_media_payload,
    media_json_from_post,
    parse_media_json,
    upload_files,
    validate_files,
)
from app.services.push_notifications import push_enabled, send_alert_notification
from app.services.recaptcha import recaptcha_enabled, verify_recaptcha
from app.services.vote_identity import get_voter_hash

from . import map_bp

URGENT_CATEGORY_SLUGS = {
    "accion-represiva",
    "accion-represiva-del-gobierno",
    "movimiento-tropas",
    "movimiento-militar",
    "desconexion-internet",
}


def _get_chat_nick():
    allow_admin = current_user.is_authenticated and current_user.has_role(
        "administrador"
    )
    if current_user.is_authenticated and current_user.anon_code:
        return f"Anon-{current_user.anon_code}"
    nick = session.get("chat_nick")
    if nick and (nick.lower() != "admin" or allow_admin):
        return nick
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    nick = f"Anon-{code}"
    session["chat_nick"] = nick
    return nick


def _get_chat_session_id():
    sid = session.get("chat_sid")
    if sid:
        return sid
    sid = secrets.token_hex(16)
    session["chat_sid"] = sid
    return sid


def _get_verified_post_ids(post_ids):
    if not post_ids:
        return set()
    voter_hash = get_voter_hash(
        current_user, request, current_app.config.get("SECRET_KEY", "")
    )
    if not voter_hash:
        return set()
    rows = (
        VoteRecord.query.filter_by(target_type="post_verify", voter_hash=voter_hash)
        .filter(VoteRecord.target_id.in_(post_ids))
        .all()
    )
    return {row.target_id for row in rows}


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


def _clean_captions(raw, count):
    captions = []
    for idx in range(count):
        value = ""
        if raw and idx < len(raw):
            value = (raw[idx] or "").strip()
        if value:
            value = value[:255]
        captions.append(value)
    return captions


@map_bp.route("/")
def dashboard():
    categories = Category.query.order_by(Category.id.asc()).all()
    posts = Post.query.filter_by(status="approved").all()
    return render_template(
        "map/dashboard.html",
        categories=categories,
        posts=posts,
        vapid_public_key=current_app.config.get("VAPID_PUBLIC_KEY"),
        push_alerts_enabled=push_enabled(),
        chat_nick=_get_chat_nick(),
        chat_sid=_get_chat_session_id(),
        irc_nick=_get_chat_nick(),
        provinces=list_provinces(),
        municipalities_map=municipalities_map(),
    )


@map_bp.route("/push-sw.js")
def push_service_worker():
    response = current_app.send_static_file("push-sw.js")
    response.headers["Cache-Control"] = "no-cache"
    return response


def _export_columns():
    return [
        ("id", "ID"),
        ("title", "Título"),
        ("description", "Descripción"),
        ("category", "Categoría"),
        ("province", "Provincia"),
        ("municipality", "Municipio"),
        ("latitude", "Latitud"),
        ("longitude", "Longitud"),
        ("address", "Dirección"),
        ("repressor_name", "Represor"),
        ("other_type", "Tipo (Otros)"),
        ("verify_count", "Verificaciones"),
        ("links", "Enlaces"),
        ("created_at", "Creado"),
        ("updated_at", "Actualizado"),
    ]


def _serialize_export_row(post):
    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json) or []
        except Exception:
            links = []
    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "category": post.category.name if post.category else "",
        "province": post.province or "",
        "municipality": post.municipality or "",
        "latitude": str(post.latitude) if post.latitude is not None else "",
        "longitude": str(post.longitude) if post.longitude is not None else "",
        "address": post.address or "",
        "repressor_name": post.repressor_name or "",
        "other_type": post.other_type or "",
        "verify_count": post.verify_count or 0,
        "links": ", ".join(links),
        "created_at": post.created_at.isoformat() if post.created_at else "",
        "updated_at": post.updated_at.isoformat() if post.updated_at else "",
    }


def _load_export_posts():
    return (
        Post.query.options(selectinload(Post.category))
        .filter_by(status="approved")
        .order_by(Post.created_at.desc())
        .all()
    )


@map_bp.route("/exportar")
def export_data():
    return render_template("map/export.html")


@map_bp.route("/exportar/descargar")
def export_download():
    fmt = (request.args.get("format") or "csv").lower()
    if fmt not in {"csv", "xls", "txt", "pdf"}:
        abort(400)

    columns = _export_columns()
    posts = _load_export_posts()
    rows = [_serialize_export_row(post) for post in posts]
    filename = f"soscubamap_reportes_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.{fmt}"

    if fmt in {"csv", "txt"}:
        output = io.StringIO()
        delimiter = "," if fmt == "csv" else "\t"
        writer = csv.writer(output, delimiter=delimiter)
        writer.writerow([label for _, label in columns])
        for row in rows:
            writer.writerow([row[key] for key, _ in columns])
        resp = make_response(output.getvalue())
        mime = "text/csv" if fmt == "csv" else "text/plain"
        resp.headers["Content-Type"] = f"{mime}; charset=utf-8"
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    if fmt == "xls":
        header_cells = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
        body_rows = []
        for row in rows:
            cells = "".join(
                f"<td>{html.escape(str(row[key] if row[key] is not None else ''))}</td>"
                for key, _ in columns
            )
            body_rows.append(f"<tr>{cells}</tr>")
        table_html = (
            '<table border="1">'
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody>"
            "</table>"
        )
        html_doc = (
            '<!doctype html><html><head><meta charset="utf-8"></head>'
            f"<body>{table_html}</body></html>"
        )
        resp = make_response(html_doc)
        resp.headers["Content-Type"] = "application/vnd.ms-excel; charset=utf-8"
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    # PDF (solo texto)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception:
        resp = make_response("PDF no disponible en el servidor.", 501)
        resp.headers["Content-Type"] = "text/plain; charset=utf-8"
        return resp

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    margin = 36
    y = height - margin
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(margin, y, "SOSCuba Map · Exportación de reportes (solo texto)")
    y -= 18
    pdf.setFont("Helvetica", 9)
    pdf.drawString(margin, y, f"Generado: {datetime.utcnow().isoformat()} UTC")
    y -= 18

    def write_line(text):
        nonlocal y
        if y < margin:
            pdf.showPage()
            y = height - margin
            pdf.setFont("Helvetica", 9)
        pdf.drawString(margin, y, text)
        y -= 12

    wrap_width = 110
    for row in rows:
        write_line(f"Reporte #{row['id']}")
        for key, label in columns:
            value = row.get(key, "")
            if value is None:
                value = ""
            text = f"{label}: {value}"
            for line in textwrap.wrap(text, width=wrap_width) or [""]:
                write_line(line)
        write_line("-" * 80)
        y -= 6

    pdf.showPage()
    pdf.save()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@map_bp.route("/api-docs")
def api_docs():
    base_url = request.host_url.rstrip("/")
    return render_template("map/api_docs.html", base_url=base_url)


@map_bp.route("/analiticas")
def analytics():
    categories = Category.query.order_by(Category.id.asc()).all()
    return render_template(
        "map/analytics.html",
        categories=categories,
        provinces=list_provinces(),
    )


@map_bp.route("/nuevo", methods=["GET", "POST"])
@limiter.limit("3/minute; 30/day", methods=["POST"])
def new_post():
    categories = sort_categories_for_forms(
        Category.query.order_by(Category.id.asc()).all()
    )
    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "category_id": request.form.get("category_id", "").strip(),
            "latitude": request.form.get("latitude", "").strip(),
            "longitude": request.form.get("longitude", "").strip(),
            "address": request.form.get("address", "").strip(),
            "province": request.form.get("province", "").strip(),
            "municipality": request.form.get("municipality", "").strip(),
            "movement_date": request.form.get("movement_date", "").strip(),
            "movement_time": request.form.get("movement_time", "").strip(),
            "repressor_name": request.form.get("repressor_name", "").strip(),
            "other_type": request.form.get("other_type", "").strip(),
            "polygon_geojson": request.form.get("polygon_geojson", "").strip(),
        }
        images = [
            file
            for file in request.files.getlist("images")
            if file and (file.filename or "").strip()
        ]
        image_captions = request.form.getlist("image_captions[]")
        links = request.form.getlist("links[]")
        links = [link.strip() for link in links if link.strip()]
        errors = {}

        if recaptcha_enabled():
            token = request.form.get("g-recaptcha-response", "")
            if not verify_recaptcha(token, request.remote_addr):
                errors["recaptcha"] = (
                    "Verificación reCAPTCHA falló. Intenta nuevamente."
                )

        if has_malicious_input(
            [
                form_data["title"],
                form_data["description"],
                form_data["address"],
                form_data["province"],
                form_data["municipality"],
                form_data["movement_date"],
                form_data["movement_time"],
                form_data["repressor_name"],
                form_data["other_type"],
            ]
            + links
        ):
            errors["form"] = (
                "Se detectó contenido sospechoso. Revisa y vuelve a intentar."
            )

        if not form_data["title"]:
            errors["title"] = "El título es obligatorio."
        if not form_data["description"]:
            errors["description"] = "La descripción es obligatoria."
        if not form_data["category_id"]:
            errors["category_id"] = "Selecciona una categoría."
        if not form_data["latitude"]:
            errors["latitude"] = "La latitud es obligatoria."
        if not form_data["longitude"]:
            errors["longitude"] = "La longitud es obligatoria."

        if form_data["title"] and "title" not in errors:
            ok_title, msg_title = validate_title(form_data["title"])
            if not ok_title:
                errors["title"] = msg_title
        if form_data["description"] and "description" not in errors:
            if len(form_data["description"]) < 50:
                errors["description"] = (
                    "La descripción debe tener al menos 50 caracteres."
                )
            else:
                ok_desc, msg_desc = validate_description(form_data["description"])
                if not ok_desc:
                    errors["description"] = msg_desc

        category = None
        if form_data["category_id"]:
            try:
                category = Category.query.get(int(form_data["category_id"]))
            except Exception:
                errors["category_id"] = "Selecciona una categoría válida."
        slug = category.slug if category else ""
        is_urgent = slug in URGENT_CATEGORY_SLUGS
        movement_at = None
        if slug == "residencia-represor":
            if not form_data["repressor_name"]:
                errors["repressor_name"] = (
                    "Debes indicar el nombre o apodo del represor."
                )
            if not images:
                errors["images"] = "Debes subir al menos una imagen del represor."
        if slug in URGENT_CATEGORY_SLUGS:
            if not form_data["movement_date"]:
                errors["movement_date"] = "Debes indicar la fecha del evento."
            if not form_data["movement_time"]:
                errors["movement_time"] = "Debes indicar la hora del evento."
            if not errors.get("movement_date") and not errors.get("movement_time"):
                try:
                    movement_at = datetime.fromisoformat(
                        f"{form_data['movement_date']}T{form_data['movement_time']}"
                    )
                except Exception:
                    errors["movement_date"] = "Fecha u hora inválida."
        if slug == "otros":
            if not form_data["other_type"]:
                errors["other_type"] = (
                    "Debes especificar el tipo en la categoría Otros."
                )
            elif not is_other_type_allowed(form_data["other_type"]):
                errors["other_type"] = (
                    "El tipo en “Otros” no puede referirse a represores. Usa la categoría correspondiente."
                )
        if images and "images" not in errors:
            ok, error = validate_files(images)
            if not ok:
                errors["images"] = error

        lat = None
        lng = None
        if "latitude" not in errors and "longitude" not in errors:
            try:
                lat = Decimal(form_data["latitude"])
                lng = Decimal(form_data["longitude"])
            except Exception:
                errors["latitude"] = "Latitud inválida."
                errors["longitude"] = "Longitud inválida."

        if lat is not None and lng is not None and not is_within_cuba_bounds(lat, lng):
            errors["latitude"] = "La ubicación debe estar dentro del territorio cubano."
            errors["longitude"] = "La ubicación debe estar dentro del territorio cubano."

        if lat is not None and lng is not None:
            province, municipality = _resolve_geo_location(
                lat, lng, form_data["province"], form_data["municipality"]
            )
            form_data["province"] = province or ""
            form_data["municipality"] = municipality or ""

        if not form_data["province"]:
            errors["province"] = "Provincia obligatoria."
        if not form_data["municipality"]:
            errors["municipality"] = "Municipio obligatorio."

        if errors:
            moderation_setting = SiteSetting.query.filter_by(
                key="moderation_enabled"
            ).first()
            moderation_enabled = True
            if moderation_setting:
                moderation_enabled = moderation_setting.value == "true"
            return render_template(
                "map/new_post.html",
                categories=categories,
                preset_lat=form_data["latitude"],
                preset_lng=form_data["longitude"],
                preset_zoom=request.args.get("zoom", ""),
                moderation_enabled=moderation_enabled,
                provinces=list_provinces(),
                municipalities_map=municipalities_map(),
                recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
                form_data=form_data,
                errors=errors,
                form_links=links,
            )

        try:
            lat = Decimal(form_data["latitude"])
            lng = Decimal(form_data["longitude"])
        except Exception:
            flash("Latitud/longitud inválidas.", "error")
            return redirect(url_for("map.new_post"))

        if not is_within_cuba_bounds(lat, lng):
            flash("La ubicación debe estar dentro del territorio cubano.", "error")
            return redirect(url_for("map.new_post"))

        province, municipality = _resolve_geo_location(
            lat, lng, form_data["province"], form_data["municipality"]
        )
        if not province or not municipality:
            flash("Provincia y municipio son obligatorios.", "error")
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

        moderation_setting = SiteSetting.query.filter_by(
            key="moderation_enabled"
        ).first()
        moderation_enabled = True
        if moderation_setting:
            moderation_enabled = moderation_setting.value == "true"

        post = Post(
            title=form_data["title"],
            description=form_data["description"],
            category_id=int(form_data["category_id"]),
            latitude=lat,
            longitude=lng,
            address=form_data["address"] or None,
            province=province or None,
            municipality=municipality or None,
            movement_at=movement_at,
            repressor_name=form_data["repressor_name"] or None,
            other_type=form_data["other_type"] or None,
            polygon_geojson=form_data["polygon_geojson"] or None,
            links_json=json.dumps(links) if links else None,
            author_id=author_id,
        )
        post.status = "approved" if is_urgent or not moderation_enabled else "pending"
        db.session.add(post)
        db.session.commit()

        if images:
            media_urls = upload_files(images)
            captions = _clean_captions(image_captions, len(media_urls))
            for idx, url in enumerate(media_urls):
                caption = captions[idx] if idx < len(captions) else ""
                db.session.add(
                    Media(post_id=post.id, file_url=url, caption=caption or None)
                )
            db.session.commit()

        if is_urgent and post.status == "approved":
            try:
                send_alert_notification(post)
            except Exception:
                current_app.logger.exception("No se pudo enviar notificación push.")

        payload = {
            "id": post.id,
            "status": post.status,
            "title": post.title,
            "description": post.description,
            "latitude": float(post.latitude),
            "longitude": float(post.longitude),
            "address": post.address,
            "category": {"name": post.category.name, "slug": post.category.slug},
            "verify_count": post.verify_count or 0,
            "created_at": post.created_at.isoformat(),
            "movement_at": post.movement_at.isoformat() if post.movement_at else None,
        }

        # If submitted from iframe modal, return a script that closes the modal and refreshes map
        if request.args.get("modal") == "1":
            return render_template("map/report_success.html", payload=payload)

        if post.status == "pending":
            flash("Reporte enviado a moderación.", "success")
        else:
            flash("Reporte publicado.", "success")
        return redirect(url_for("map.dashboard"))

    preset_lat = request.args.get("lat", "")
    preset_lng = request.args.get("lng", "")
    preset_zoom = request.args.get("zoom", "")
    preset_province = ""
    preset_municipality = ""
    if preset_lat and preset_lng:
        try:
            lat = Decimal(preset_lat)
            lng = Decimal(preset_lng)
            preset_province, preset_municipality = _resolve_geo_location(
                lat, lng, "", ""
            )
        except Exception:
            preset_province = ""
            preset_municipality = ""
    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"

    return render_template(
        "map/new_post.html",
        categories=categories,
        preset_lat=preset_lat,
        preset_lng=preset_lng,
        preset_zoom=preset_zoom,
        preset_province=preset_province,
        preset_municipality=preset_municipality,
        moderation_enabled=moderation_enabled,
        provinces=list_provinces(),
        municipalities_map=municipalities_map(),
        recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
        form_data=None,
        errors={},
        form_links=[],
    )


@map_bp.route("/donar")
def donate():
    logs = DonationLog.query.order_by(DonationLog.donated_at.desc()).all()
    return render_template("map/donate.html", donation_logs=logs)


@map_bp.route("/acerca")
def about():
    return render_template("map/about.html")


@map_bp.route("/reportar-ubicacion/<int:post_id>", methods=["GET", "POST"])
@limiter.limit("5/minute; 50/day", methods=["POST"])
def report_location(post_id):
    post = Post.query.get_or_404(post_id)
    submitted = False
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if has_malicious_input([message]):
            flash(
                "Se detectó contenido sospechoso. Revisa y vuelve a intentar.", "error"
            )
        elif not message:
            flash("Describe por qué la ubicación es incorrecta.", "error")
        else:
            db.session.add(LocationReport(post_id=post.id, message=message))
            db.session.commit()
            submitted = True
    return render_template("map/report_location.html", post=post, submitted=submitted)


def _get_or_create_anon_editor():
    if current_user.is_authenticated:
        return current_user
    anon_user = User(email=f"anon+{secrets.token_hex(6)}@local")
    anon_user.set_password(secrets.token_urlsafe(16))
    anon_user.ensure_anon_code()
    default_role = Role.query.filter_by(name="colaborador").first()
    if default_role:
        anon_user.roles.append(default_role)
    db.session.add(anon_user)
    db.session.flush()
    return anon_user


def _is_admin_user():
    return current_user.is_authenticated and current_user.has_role("administrador")


def _is_edit_locked(post: Post) -> bool:
    return (post.verify_count or 0) >= 10 and not _is_admin_user()


@map_bp.route("/reporte/<int:post_id>/editar", methods=["GET", "POST"])
@limiter.limit("3/minute; 30/day", methods=["POST"])
def edit_report_public(post_id):
    post = Post.query.get_or_404(post_id)
    if _is_edit_locked(post):
        message = (
            "Este reporte ya tiene 10 verificaciones y solo el admin puede editarlo. "
            "Aun puedes comentar notas y reportar ubicacion si detectas un dato erroneo."
        )
        if request.args.get("modal") == "1":
            return render_template(
                "map/edit_locked.html", message=message, post_id=post.id
            )
        flash(message, "error")
        return redirect(url_for("map.report_detail", post_id=post.id))
    categories = sort_categories_for_forms(
        Category.query.order_by(Category.id.asc()).all()
    )
    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []

    if request.method == "POST":
        form_data = {
            "title": request.form.get("title", "").strip(),
            "description": request.form.get("description", "").strip(),
            "edit_reason": request.form.get("edit_reason", "").strip(),
            "category_id": request.form.get("category_id", "").strip(),
            "latitude": request.form.get("latitude", "").strip(),
            "longitude": request.form.get("longitude", "").strip(),
            "address": request.form.get("address", "").strip(),
            "province": request.form.get("province", "").strip(),
            "municipality": request.form.get("municipality", "").strip(),
            "movement_date": request.form.get("movement_date", "").strip(),
            "movement_time": request.form.get("movement_time", "").strip(),
            "repressor_name": request.form.get("repressor_name", "").strip(),
            "other_type": request.form.get("other_type", "").strip(),
            "polygon_geojson": request.form.get("polygon_geojson", "").strip(),
        }
        images = [
            file
            for file in request.files.getlist("images")
            if file and (file.filename or "").strip()
        ]
        image_captions = request.form.getlist("image_captions[]")
        links_list = request.form.getlist("links[]")
        links_list = [link.strip() for link in links_list if link.strip()]
        errors = {}

        if recaptcha_enabled():
            token = request.form.get("g-recaptcha-response", "")
            if not verify_recaptcha(token, request.remote_addr):
                errors["recaptcha"] = (
                    "Verificación reCAPTCHA falló. Intenta nuevamente."
                )

        if has_malicious_input(
            [
                form_data["title"],
                form_data["description"],
                form_data["edit_reason"],
                form_data["address"],
                form_data["province"],
                form_data["municipality"],
                form_data["movement_date"],
                form_data["movement_time"],
                form_data["repressor_name"],
                form_data["other_type"],
            ]
            + links_list
        ):
            errors["form"] = (
                "Se detectó contenido sospechoso. Revisa y vuelve a intentar."
            )

        if not form_data["title"]:
            errors["title"] = "El título es obligatorio."
        if not form_data["description"]:
            errors["description"] = "La descripción es obligatoria."
        if not form_data["edit_reason"]:
            errors["edit_reason"] = "El motivo de edición es obligatorio."
        if not form_data["category_id"]:
            errors["category_id"] = "Selecciona una categoría."
        if not form_data["latitude"]:
            errors["latitude"] = "La latitud es obligatoria."
        if not form_data["longitude"]:
            errors["longitude"] = "La longitud es obligatoria."

        if form_data["title"] and "title" not in errors:
            ok_title, msg_title = validate_title(form_data["title"])
            if not ok_title:
                errors["title"] = msg_title
        if form_data["description"] and "description" not in errors:
            if len(form_data["description"]) < 50:
                errors["description"] = (
                    "La descripción debe tener al menos 50 caracteres."
                )
            else:
                ok_desc, msg_desc = validate_description(form_data["description"])
                if not ok_desc:
                    errors["description"] = msg_desc

        category = None
        if form_data["category_id"]:
            try:
                category = Category.query.get(int(form_data["category_id"]))
            except Exception:
                errors["category_id"] = "Selecciona una categoría válida."
        slug = category.slug if category else ""
        is_urgent = slug in URGENT_CATEGORY_SLUGS
        existing_media_count = len(get_media_payload(post))
        movement_at = None
        if slug == "residencia-represor":
            if not form_data["repressor_name"]:
                errors["repressor_name"] = (
                    "Debes indicar el nombre o apodo del represor."
                )
            if existing_media_count + len(images) < 1:
                errors["images"] = "Debes subir al menos una imagen del represor."
        if slug in URGENT_CATEGORY_SLUGS:
            if not form_data["movement_date"]:
                errors["movement_date"] = "Debes indicar la fecha del evento."
            if not form_data["movement_time"]:
                errors["movement_time"] = "Debes indicar la hora del evento."
            if not errors.get("movement_date") and not errors.get("movement_time"):
                try:
                    movement_at = datetime.fromisoformat(
                        f"{form_data['movement_date']}T{form_data['movement_time']}"
                    )
                except Exception:
                    errors["movement_date"] = "Fecha u hora inválida."
        if slug == "otros":
            if not form_data["other_type"]:
                errors["other_type"] = (
                    "Debes especificar el tipo en la categoría Otros."
                )
            elif not is_other_type_allowed(form_data["other_type"]):
                errors["other_type"] = (
                    "El tipo en “Otros” no puede referirse a represores. Usa la categoría correspondiente."
                )
        if images and "images" not in errors:
            ok, error = validate_files(images)
            if not ok:
                errors["images"] = error

        lat = None
        lng = None
        if "latitude" not in errors and "longitude" not in errors:
            try:
                lat = Decimal(form_data["latitude"])
                lng = Decimal(form_data["longitude"])
            except Exception:
                errors["latitude"] = "Latitud inválida."
                errors["longitude"] = "Longitud inválida."

        if lat is not None and lng is not None:
            province, municipality = _resolve_geo_location(
                lat, lng, form_data["province"], form_data["municipality"]
            )
            form_data["province"] = province or ""
            form_data["municipality"] = municipality or ""

        if not form_data["province"]:
            errors["province"] = "Provincia obligatoria."
        if not form_data["municipality"]:
            errors["municipality"] = "Municipio obligatorio."

        if errors:
            moderation_setting = SiteSetting.query.filter_by(
                key="moderation_enabled"
            ).first()
            moderation_enabled = True
            if moderation_setting:
                moderation_enabled = moderation_setting.value == "true"
            return render_template(
                "map/edit_report.html",
                post=post,
                categories=categories,
                links=links,
                form_links=links_list,
                form_data=form_data,
                errors=errors,
                media_items=get_media_payload(post),
                moderation_enabled=moderation_enabled,
                provinces=list_provinces(),
                municipalities_map=municipalities_map(),
                recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
            )

        try:
            lat = Decimal(form_data["latitude"])
            lng = Decimal(form_data["longitude"])
        except Exception:
            flash("Latitud/longitud inválidas.", "error")
            return redirect(url_for("map.edit_report_public", post_id=post.id))

        province, municipality = _resolve_geo_location(
            lat, lng, form_data["province"], form_data["municipality"]
        )
        if not province or not municipality:
            flash("Provincia y municipio son obligatorios.", "error")
            return redirect(url_for("map.edit_report_public", post_id=post.id))

        moderation_setting = SiteSetting.query.filter_by(
            key="moderation_enabled"
        ).first()
        moderation_enabled = True
        if moderation_setting:
            moderation_enabled = moderation_setting.value == "true"

        editor = _get_or_create_anon_editor()
        editor_label = (
            f"Anon-{editor.anon_code}" if editor and editor.anon_code else "Anon"
        )
        media_urls = []
        media_items = []
        if images:
            media_urls = upload_files(images)
            if not media_urls:
                flash("No se pudo subir la imagen.", "error")
                return redirect(url_for("map.edit_report_public", post_id=post.id))
            captions = _clean_captions(image_captions, len(media_urls))
            media_items = [
                {"url": url, "caption": (captions[idx] if idx < len(captions) else "")}
                for idx, url in enumerate(media_urls)
            ]

        if moderation_enabled and not is_urgent:
            combined_media = None
            if media_items:
                combined_media = get_media_payload(post) + media_items
            edit_req = PostEditRequest(
                post_id=post.id,
                editor_id=editor.id if editor else None,
                editor_label=editor_label,
                reason=form_data["edit_reason"],
                title=form_data["title"],
                description=form_data["description"],
                latitude=lat,
                longitude=lng,
                address=form_data["address"] or None,
                province=province or None,
                municipality=municipality or None,
                movement_at=movement_at,
                repressor_name=form_data["repressor_name"] or None,
                other_type=form_data["other_type"] or None,
                category_id=int(form_data["category_id"]),
                polygon_geojson=form_data["polygon_geojson"] or None,
                links_json=json.dumps(links_list) if links_list else None,
                media_json=(
                    json.dumps(combined_media) if combined_media is not None else None
                ),
            )
            db.session.add(edit_req)
            db.session.commit()
            payload = {"status": "pending"}
            if request.args.get("modal") == "1":
                return render_template("map/edit_success.html", payload=payload)
            flash("Edición enviada a moderación.", "success")
            return redirect(url_for("map.dashboard"))

        # Sin moderación: aplicar directo y guardar revisión
        revision = PostRevision(
            post_id=post.id,
            editor_id=editor.id if editor else None,
            editor_label=editor_label,
            reason=form_data["edit_reason"],
            title=post.title,
            description=post.description,
            latitude=post.latitude,
            longitude=post.longitude,
            address=post.address,
            province=post.province,
            municipality=post.municipality,
            movement_at=post.movement_at,
            repressor_name=post.repressor_name,
            other_type=post.other_type,
            category_id=post.category_id,
            polygon_geojson=post.polygon_geojson,
            links_json=post.links_json,
            media_json=media_json_from_post(post),
        )
        db.session.add(revision)

        post.title = form_data["title"]
        post.description = form_data["description"]
        post.category_id = int(form_data["category_id"])
        post.latitude = lat
        post.longitude = lng
        post.address = form_data["address"] or None
        post.province = province or None
        post.municipality = municipality or None
        post.movement_at = movement_at
        post.repressor_name = form_data["repressor_name"] or None
        post.other_type = form_data["other_type"] or None
        post.polygon_geojson = form_data["polygon_geojson"] or None
        post.links_json = json.dumps(links_list) if links_list else None
        if media_items:
            for item in media_items:
                db.session.add(
                    Media(
                        post_id=post.id,
                        file_url=item.get("url"),
                        caption=(item.get("caption") or None),
                    )
                )
        db.session.commit()

        payload = {"status": "approved"}
        if request.args.get("modal") == "1":
            return render_template("map/edit_success.html", payload=payload)
        flash("Edición aplicada.", "success")
        return redirect(url_for("map.dashboard"))

    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"

    return render_template(
        "map/edit_report.html",
        post=post,
        categories=categories,
        links=links,
        media_items=get_media_payload(post),
        moderation_enabled=moderation_enabled,
        provinces=list_provinces(),
        municipalities_map=municipalities_map(),
        recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
        form_data=None,
        errors={},
        form_links=links,
    )


@map_bp.route("/reporte/<int:post_id>")
def report_detail(post_id):
    post = Post.query.get_or_404(post_id)
    if post.status != "approved":
        allowed = current_user.is_authenticated and (
            current_user.has_role("moderador") or current_user.has_role("administrador")
        )
        if not allowed:
            abort(404)

    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []

    anon_label = (
        f"Anon-{post.author.anon_code}"
        if post.author and post.author.anon_code
        else "Anon"
    )
    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"
    verified_by_me = post.id in _get_verified_post_ids([post.id])
    return render_template(
        "map/report_detail.html",
        post=post,
        links=links,
        anon_label=anon_label,
        media_items=get_media_payload(post),
        moderation_enabled=moderation_enabled,
        edit_locked=_is_edit_locked(post),
        recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
        verified_by_me=verified_by_me,
    )


@map_bp.route("/reporte/<int:post_id>/historial")
def post_history(post_id):
    post = Post.query.get_or_404(post_id)
    revisions = (
        PostRevision.query.filter_by(post_id=post.id)
        .order_by(PostRevision.created_at.desc())
        .all()
    )
    rejected_edits = (
        PostEditRequest.query.filter_by(post_id=post.id, status="rejected")
        .order_by(PostEditRequest.created_at.desc())
        .all()
    )
    latest_reason = None
    if revisions:
        latest_reason = revisions[0].reason
    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []
    rev_links = {}
    rev_media = {}
    for rev in revisions:
        if rev.links_json:
            try:
                rev_links[rev.id] = json.loads(rev.links_json)
            except Exception:
                rev_links[rev.id] = []
        else:
            rev_links[rev.id] = []
        if rev.media_json:
            rev_media[rev.id] = parse_media_json(rev.media_json)
        else:
            rev_media[rev.id] = []

    rejected_links = {}
    rejected_media = {}
    for edit in rejected_edits:
        if edit.links_json:
            try:
                rejected_links[edit.id] = json.loads(edit.links_json)
            except Exception:
                rejected_links[edit.id] = []
        else:
            rejected_links[edit.id] = []
        if edit.media_json:
            rejected_media[edit.id] = parse_media_json(edit.media_json)
        else:
            rejected_media[edit.id] = []

    return render_template(
        "map/post_history.html",
        post=post,
        revisions=revisions,
        links=links,
        rev_links=rev_links,
        latest_reason=latest_reason,
        media_items=get_media_payload(post),
        rev_media=rev_media,
        rejected_edits=rejected_edits,
        rejected_links=rejected_links,
        rejected_media=rejected_media,
    )


@map_bp.route("/reportes")
def reports():
    selected_province = request.args.get("provincia", "").strip()
    selected_municipality = request.args.get("municipio", "").strip()

    query = Post.query.filter_by(status="approved")
    if selected_province:
        query = query.filter_by(province=selected_province)
    if selected_municipality:
        query = query.filter_by(municipality=selected_municipality)

    posts = query.order_by(Post.created_at.desc()).all()
    verified_ids = _get_verified_post_ids([post.id for post in posts])

    provinces = list_provinces()
    if selected_province:
        municipalities = list_municipalities(selected_province)
    else:
        municipalities = list_municipalities()

    return render_template(
        "map/reports.html",
        posts=posts,
        verified_ids=verified_ids,
        provinces=provinces,
        municipalities=municipalities,
        selected_province=selected_province,
        selected_municipality=selected_municipality,
        municipalities_map=municipalities_map(),
    )
