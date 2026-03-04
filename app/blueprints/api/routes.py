from flask import jsonify, request, make_response, session, current_app
import math
import json
import secrets
from datetime import datetime, timedelta
from flask_login import current_user

from app.extensions import db, limiter
from app.services.input_safety import has_malicious_input
from app.services.recaptcha import verify_recaptcha, recaptcha_enabled
from app.services.text_sanitize import sanitize_text
from app.models.comment import Comment
from app.models.user import User
from app.models.role import Role
from app.models.media import Media
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.site_setting import SiteSetting
from app.services.media_upload import (
    validate_files,
    upload_files,
    media_json_from_post,
    get_media_payload,
)
from app.models.chat_message import ChatMessage
from app.models.chat_presence import ChatPresence
from app.models.discussion_post import DiscussionPost
from app.models.discussion_comment import DiscussionComment

from app.models.post import Post
from sqlalchemy.orm import selectinload
from app.models.category import Category
from sqlalchemy import func
from . import api_bp


def _is_admin_user():
    return current_user.is_authenticated and current_user.has_role("administrador")


def _get_chat_nick():
    nick = session.get("chat_nick")
    if nick and (nick.lower() != "admin" or _is_admin_user()):
        return nick
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "".join(secrets.choice(alphabet) for _ in range(6))
    nick = f"Anon-{code}"
    session["chat_nick"] = nick
    return nick


def _sanitize_nick(nickname: str, fallback: str) -> str:
    value = (nickname or "").strip()
    if not value:
        return fallback
    if value.lower() == "admin" and not _is_admin_user():
        return fallback
    return value[:80]


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.route("/categories")
def categories():
    items = Category.query.order_by(Category.id.asc()).all()
    return jsonify(
        [
            {"id": c.id, "name": c.name, "slug": c.slug, "description": c.description}
            for c in items
        ]
    )


@api_bp.route("/posts")
def posts():
    category_id = request.args.get("category_id")
    limit = request.args.get("limit")
    query = Post.query.options(selectinload(Post.media)).filter_by(status="approved")
    if category_id:
        query = query.filter_by(category_id=int(category_id))

    query = query.order_by(Post.created_at.desc())
    if limit:
        try:
            query = query.limit(int(limit))
        except ValueError:
            pass

    items = query.all()
    return jsonify(
        [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "latitude": float(p.latitude),
                "longitude": float(p.longitude),
                "address": p.address,
                "province": p.province,
                "municipality": p.municipality,
                "repressor_name": p.repressor_name,
                "other_type": p.other_type,
                "created_at": p.created_at.isoformat(),
                "anon": f"Anon-{p.author.anon_code}" if p.author and p.author.anon_code else "Anon",
                "polygon_geojson": p.polygon_geojson,
                "links": json.loads(p.links_json) if p.links_json else [],
                "media": get_media_payload(p)[:4],
                "verify_count": p.verify_count or 0,
                "category": {
                    "id": p.category.id,
                    "name": p.category.name,
                    "slug": p.category.slug,
                },
            }
            for p in items
        ]
    )


def _serialize_post(post: Post):
    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "latitude": float(post.latitude),
        "longitude": float(post.longitude),
        "address": post.address,
        "province": post.province,
        "municipality": post.municipality,
        "repressor_name": post.repressor_name,
        "other_type": post.other_type,
        "status": post.status,
        "polygon_geojson": post.polygon_geojson,
        "links": json.loads(post.links_json) if post.links_json else [],
        "media": get_media_payload(post),
        "verify_count": post.verify_count or 0,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "anon": f"Anon-{post.author.anon_code}" if post.author and post.author.anon_code else "Anon",
        "category": {
            "id": post.category.id,
            "name": post.category.name,
            "slug": post.category.slug,
        }
        if post.category
        else None,
    }


@api_bp.route("/v1/reports")
@limiter.limit("120/minute")
def reports_v1():
    category_id = request.args.get("category_id")
    province = (request.args.get("province") or "").strip()
    municipality = (request.args.get("municipality") or "").strip()
    status = (request.args.get("status") or "approved").strip().lower()

    allowed_statuses = {"pending", "approved", "rejected", "hidden", "deleted"}
    if status not in allowed_statuses:
        status = "approved"

    if status != "approved" and not _is_admin_user():
        status = "approved"

    query = Post.query.options(
        selectinload(Post.media),
        selectinload(Post.category),
        selectinload(Post.author),
    )
    query = query.filter(Post.status == status)

    if category_id:
        try:
            query = query.filter(Post.category_id == int(category_id))
        except ValueError:
            pass

    if province:
        query = query.filter(Post.province.ilike(province))
    if municipality:
        query = query.filter(Post.municipality.ilike(municipality))

    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        per_page = max(int(request.args.get("per_page", 50)), 1)
    except ValueError:
        per_page = 50
    per_page = min(per_page, 100)

    total = query.count()
    pages = max(math.ceil(total / per_page), 1) if per_page else 1
    items = (
        query.order_by(Post.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify(
        {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1,
            "items": [_serialize_post(p) for p in items],
        }
    )


@api_bp.route("/v1/reports/<int:post_id>")
@limiter.limit("120/minute")
def report_detail_v1(post_id):
    query = Post.query.options(
        selectinload(Post.media),
        selectinload(Post.category),
        selectinload(Post.author),
    )
    post = query.get_or_404(post_id)
    if post.status != "approved" and not _is_admin_user():
        return jsonify({"error": "No autorizado."}), 403
    return jsonify(_serialize_post(post))


@api_bp.route("/v1/categories")
def categories_v1():
    return categories()


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        return None


@api_bp.route("/v1/analytics")
@limiter.limit("60/minute")
def analytics_v1():
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()
    category_id = request.args.get("category_id")
    province = (request.args.get("province") or "").strip()

    end_dt = _parse_date(end_raw) or datetime.utcnow()
    start_dt = _parse_date(start_raw) or (end_dt - timedelta(days=90))
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)

    active_statuses = ["approved", "pending", "rejected", "hidden"]

    base_query = Post.query.filter(
        Post.created_at >= start_dt,
        Post.created_at <= end_dt,
        Post.status.in_(active_statuses),
    )
    if category_id:
        try:
            base_query = base_query.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        base_query = base_query.filter(Post.province == province)

    reports_over_time = (
        db.session.query(
            func.date_trunc("day", Post.created_at).label("day"),
            func.count(Post.id),
        )
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
        )
        .group_by(func.date_trunc("day", Post.created_at))
        .order_by(func.date_trunc("day", Post.created_at))
    )
    if category_id:
        try:
            reports_over_time = reports_over_time.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        reports_over_time = reports_over_time.filter(Post.province == province)

    reports_series = [
        {"date": row[0].date().isoformat(), "count": row[1]}
        for row in reports_over_time.all()
    ]

    category_distribution = (
        db.session.query(Category.id, Category.name, func.count(Post.id))
        .join(Post, Post.category_id == Category.id)
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
        )
        .group_by(Category.id, Category.name)
        .order_by(func.count(Post.id).desc())
    )
    if category_id:
        try:
            category_distribution = category_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        category_distribution = category_distribution.filter(Post.province == province)

    category_items = [
        {"id": row[0], "name": row[1], "count": row[2]}
        for row in category_distribution.all()
    ]

    province_distribution = (
        db.session.query(Post.province, func.count(Post.id))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
            Post.province.isnot(None),
            Post.province != "",
        )
        .group_by(Post.province)
        .order_by(func.count(Post.id).desc())
        .limit(10)
    )
    if category_id:
        try:
            province_distribution = province_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        province_distribution = province_distribution.filter(Post.province == province)

    province_items = [
        {"name": row[0], "count": row[1]} for row in province_distribution.all()
    ]

    municipality_distribution = (
        db.session.query(Post.municipality, func.count(Post.id))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status.in_(active_statuses),
            Post.municipality.isnot(None),
            Post.municipality != "",
        )
        .group_by(Post.municipality)
        .order_by(func.count(Post.id).desc())
        .limit(10)
    )
    if category_id:
        try:
            municipality_distribution = municipality_distribution.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        municipality_distribution = municipality_distribution.filter(Post.province == province)

    municipality_items = [
        {"name": row[0], "count": row[1]} for row in municipality_distribution.all()
    ]

    moderation_status = (
        db.session.query(Post.status, func.count(Post.id))
        .filter(Post.created_at >= start_dt, Post.created_at <= end_dt)
        .group_by(Post.status)
        .all()
    )
    moderation_map = {status: count for status, count in moderation_status}

    top_verified = (
        Post.query.options(selectinload(Post.category))
        .filter(
            Post.created_at >= start_dt,
            Post.created_at <= end_dt,
            Post.status == "approved",
        )
        .order_by(Post.verify_count.desc().nullslast(), Post.created_at.desc())
    )
    if category_id:
        try:
            top_verified = top_verified.filter(Post.category_id == int(category_id))
        except ValueError:
            pass
    if province:
        top_verified = top_verified.filter(Post.province == province)

    top_verified_items = [
        {"id": p.id, "title": p.title, "verify_count": p.verify_count or 0}
        for p in top_verified.limit(10).all()
    ]

    comment_query = (
        db.session.query(
            func.date_trunc("day", Comment.created_at).label("day"),
            func.count(Comment.id),
        )
        .filter(Comment.created_at >= start_dt, Comment.created_at <= end_dt)
        .group_by(func.date_trunc("day", Comment.created_at))
        .order_by(func.date_trunc("day", Comment.created_at))
    )
    discussion_comment_query = (
        db.session.query(
            func.date_trunc("day", DiscussionComment.created_at).label("day"),
            func.count(DiscussionComment.id),
        )
        .filter(
            DiscussionComment.created_at >= start_dt,
            DiscussionComment.created_at <= end_dt,
        )
        .group_by(func.date_trunc("day", DiscussionComment.created_at))
        .order_by(func.date_trunc("day", DiscussionComment.created_at))
    )

    report_comments = {row[0].date().isoformat(): row[1] for row in comment_query.all()}
    discussion_comments = {
        row[0].date().isoformat(): row[1] for row in discussion_comment_query.all()
    }
    labels = sorted(set(report_comments.keys()) | set(discussion_comments.keys()))
    report_counts = [report_comments.get(label, 0) for label in labels]
    discussion_counts = [discussion_comments.get(label, 0) for label in labels]

    edit_status_query = (
        db.session.query(PostEditRequest.status, func.count(PostEditRequest.id))
        .filter(PostEditRequest.created_at >= start_dt, PostEditRequest.created_at <= end_dt)
        .group_by(PostEditRequest.status)
        .all()
    )
    edit_status_map = {status: count for status, count in edit_status_query}

    return jsonify(
        {
            "range": {
                "start": start_dt.date().isoformat(),
                "end": end_dt.date().isoformat(),
            },
            "reports_over_time": reports_series,
            "category_distribution": category_items,
            "province_distribution": province_items,
            "municipality_distribution": municipality_items,
            "moderation_status": {
                "approved": moderation_map.get("approved", 0),
                "pending": moderation_map.get("pending", 0),
                "rejected": moderation_map.get("rejected", 0),
                "hidden": moderation_map.get("hidden", 0),
            },
            "top_verified": top_verified_items,
            "comments_over_time": {
                "labels": labels,
                "report_counts": report_counts,
                "discussion_counts": discussion_counts,
            },
            "edit_status": {
                "pending": edit_status_map.get("pending", 0),
                "approved": edit_status_map.get("approved", 0),
                "rejected": edit_status_map.get("rejected", 0),
            },
        }
    )


def _get_or_create_anon_user():
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


@api_bp.route("/posts/<int:post_id>/verify", methods=["POST"])
@limiter.limit("10/minute; 200/day")
def verify_post(post_id):
    post = Post.query.get_or_404(post_id)
    cookie_key = f"verified_{post_id}"
    if request.cookies.get(cookie_key):
        return jsonify({"ok": False, "verify_count": post.verify_count or 0})

    post.verify_count = (post.verify_count or 0) + 1
    db.session.commit()

    resp = make_response(jsonify({"ok": True, "verify_count": post.verify_count}))
    resp.set_cookie(cookie_key, "1")
    return resp


@api_bp.route("/posts/<int:post_id>/comments", methods=["GET", "POST"])
@limiter.limit("10/minute; 200/day", methods=["POST"])
def comments(post_id):
    post = Post.query.get_or_404(post_id)
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        body = sanitize_text(data.get("body") or "", max_len=4000)
        if recaptcha_enabled():
            token = (data.get("recaptcha") or "").strip()
            if not verify_recaptcha(token, request.remote_addr):
                return jsonify({"ok": False, "error": "Verificación reCAPTCHA falló."}), 400
        if has_malicious_input([body]):
            return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400
        if not body:
            return jsonify({"ok": False, "error": "Comentario vacío."}), 400

        user = _get_or_create_anon_user()
        label = f"Anon-{user.anon_code}" if user and user.anon_code else "Anon"
        comment = Comment(post_id=post.id, author_id=user.id, author_label=label, body=body)
        db.session.add(comment)
        db.session.commit()

    items = (
        Comment.query.filter_by(post_id=post.id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": c.id,
                "author": c.author_label or "Anon",
                "body": c.body,
                "created_at": c.created_at.isoformat(),
                "upvotes": c.upvotes or 0,
                "downvotes": c.downvotes or 0,
                "score": (c.upvotes or 0) - (c.downvotes or 0),
            }
            for c in items
        ]
    )


@api_bp.route("/comments/<int:comment_id>/vote", methods=["POST"])
@limiter.limit("30/minute; 500/day")
def vote_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    cookie_key = f"comment_vote_{comment_id}"
    prev = request.cookies.get(cookie_key)
    prev_val = None
    if prev in ("1", "-1"):
        prev_val = int(prev)

    if prev_val == value:
        resp = make_response(
            jsonify(
                {
                    "ok": True,
                    "upvotes": comment.upvotes or 0,
                    "downvotes": comment.downvotes or 0,
                    "score": (comment.upvotes or 0) - (comment.downvotes or 0),
                }
            )
        )
        resp.set_cookie(cookie_key, str(value))
        return resp

    if prev_val == 1:
        comment.upvotes = max((comment.upvotes or 0) - 1, 0)
    elif prev_val == -1:
        comment.downvotes = max((comment.downvotes or 0) - 1, 0)

    if value == 1:
        comment.upvotes = (comment.upvotes or 0) + 1
    else:
        comment.downvotes = (comment.downvotes or 0) + 1
    db.session.commit()

    resp = make_response(
        jsonify(
            {
                "ok": True,
                "upvotes": comment.upvotes or 0,
                "downvotes": comment.downvotes or 0,
                "score": (comment.upvotes or 0) - (comment.downvotes or 0),
            }
        )
    )
    resp.set_cookie(cookie_key, str(value))
    return resp


@api_bp.route("/comments/<int:comment_id>", methods=["DELETE"])
@limiter.limit("10/minute; 100/day")
def delete_comment(comment_id):
    if not (current_user.is_authenticated and current_user.has_role("administrador")):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    return jsonify({"ok": True})


@api_bp.route("/posts/<int:post_id>/status", methods=["POST"])
def update_post_status(post_id):
    if not (current_user.is_authenticated and current_user.has_role("administrador")):
        return jsonify({"ok": False, "error": "No autorizado."}), 403
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"approved", "hidden", "deleted", "rejected", "pending"}:
        return jsonify({"ok": False, "error": "Estado inválido."}), 400
    post = Post.query.get_or_404(post_id)
    post.status = status
    db.session.commit()
    return jsonify({"ok": True, "status": post.status})


@api_bp.route("/discusiones/<int:post_id>/vote", methods=["POST"])
def vote_discussion_post(post_id):
    post = DiscussionPost.query.get_or_404(post_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    cookie_key = f"discussion_post_vote_{post_id}"
    prev = request.cookies.get(cookie_key)
    prev_val = None
    if prev in ("1", "-1"):
        prev_val = int(prev)

    if prev_val == value:
        resp = make_response(
            jsonify(
                {
                    "ok": True,
                    "upvotes": post.upvotes or 0,
                    "downvotes": post.downvotes or 0,
                    "score": (post.upvotes or 0) - (post.downvotes or 0),
                }
            )
        )
        resp.set_cookie(cookie_key, str(value))
        return resp

    if prev_val == 1:
        post.upvotes = max((post.upvotes or 0) - 1, 0)
    elif prev_val == -1:
        post.downvotes = max((post.downvotes or 0) - 1, 0)

    if value == 1:
        post.upvotes = (post.upvotes or 0) + 1
    else:
        post.downvotes = (post.downvotes or 0) + 1
    db.session.commit()

    resp = make_response(
        jsonify(
            {
                "ok": True,
                "upvotes": post.upvotes or 0,
                "downvotes": post.downvotes or 0,
                "score": (post.upvotes or 0) - (post.downvotes or 0),
            }
        )
    )
    resp.set_cookie(cookie_key, str(value))
    return resp


@api_bp.route("/discusiones/comentarios/<int:comment_id>/vote", methods=["POST"])
@limiter.limit("30/minute; 500/day")
def vote_discussion_comment(comment_id):
    comment = DiscussionComment.query.get_or_404(comment_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    cookie_key = f"discussion_comment_vote_{comment_id}"
    prev = request.cookies.get(cookie_key)
    prev_val = None
    if prev in ("1", "-1"):
        prev_val = int(prev)

    if prev_val == value:
        resp = make_response(
            jsonify(
                {
                    "ok": True,
                    "upvotes": comment.upvotes or 0,
                    "downvotes": comment.downvotes or 0,
                    "score": (comment.upvotes or 0) - (comment.downvotes or 0),
                }
            )
        )
        resp.set_cookie(cookie_key, str(value))
        return resp

    if prev_val == 1:
        comment.upvotes = max((comment.upvotes or 0) - 1, 0)
    elif prev_val == -1:
        comment.downvotes = max((comment.downvotes or 0) - 1, 0)

    if value == 1:
        comment.upvotes = (comment.upvotes or 0) + 1
    else:
        comment.downvotes = (comment.downvotes or 0) + 1
    db.session.commit()

    resp = make_response(
        jsonify(
            {
                "ok": True,
                "upvotes": comment.upvotes or 0,
                "downvotes": comment.downvotes or 0,
                "score": (comment.upvotes or 0) - (comment.downvotes or 0),
            }
        )
    )
    resp.set_cookie(cookie_key, str(value))
    return resp


@api_bp.route("/posts/<int:post_id>/media", methods=["POST"])
@limiter.limit("6/hour; 30/day")
def upload_post_media(post_id):
    post = Post.query.get_or_404(post_id)
    files = [
        file
        for file in request.files.getlist("images")
        if file and (file.filename or "").strip()
    ]
    captions_raw = request.form.getlist("image_captions[]")
    if has_malicious_input(captions_raw):
        return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400
    ok, error = validate_files(files)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    moderation_setting = SiteSetting.query.filter_by(key="moderation_enabled").first()
    moderation_enabled = True
    if moderation_setting:
        moderation_enabled = moderation_setting.value == "true"

    urls = upload_files(files)
    if not urls:
        return jsonify({"ok": False, "error": "No se pudo subir la imagen."}), 400

    if moderation_enabled:
        captions = []
        for idx in range(len(urls)):
            value = ""
            if idx < len(captions_raw):
                value = (captions_raw[idx] or "").strip()
            captions.append(value[:255] if value else "")
        new_items = [
            {"url": url, "caption": (captions[idx] if idx < len(captions) else "")}
            for idx, url in enumerate(urls)
        ]
        combined = get_media_payload(post) + new_items
        edit = PostEditRequest(
            post_id=post.id,
            editor_id=current_user.id if current_user.is_authenticated else None,
            editor_label=f"Anon-{current_user.anon_code}" if current_user.is_authenticated and current_user.anon_code else "Anon",
            reason="Imagen añadida",
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
            media_json=json.dumps(combined),
        )
        db.session.add(edit)
        db.session.commit()
        return jsonify({"ok": True, "status": "pending"})

    revision = PostRevision(
        post_id=post.id,
        editor_id=current_user.id if current_user.is_authenticated else None,
        editor_label=f"Anon-{current_user.anon_code}" if current_user.is_authenticated and current_user.anon_code else "Anon",
        reason="Imagen añadida",
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

    captions = []
    for idx in range(len(urls)):
        value = ""
        if idx < len(captions_raw):
            value = (captions_raw[idx] or "").strip()
        captions.append(value[:255] if value else "")

    for idx, url in enumerate(urls):
        caption = captions[idx] if idx < len(captions) else ""
        db.session.add(Media(post_id=post.id, file_url=url, caption=caption or None))
    db.session.commit()

    return jsonify({"ok": True, "status": "approved", "media": get_media_payload(post)})


@api_bp.route("/chat", methods=["GET", "POST"])
@limiter.limit("60/minute", methods=["GET"])
@limiter.limit("6/minute; 120/day", methods=["POST"])
def chat_messages():
    if current_app.config.get("CHAT_DISABLED", True):
        return jsonify({"ok": False, "error": "Chat deshabilitado."}), 403
    now = datetime.utcnow()
    cutoff_keep = now - timedelta(hours=48)
    cutoff_visible = now - timedelta(hours=24)
    cutoff_online = now - timedelta(minutes=10)

    ChatMessage.query.filter(ChatMessage.created_at < cutoff_keep).delete()
    ChatPresence.query.filter(ChatPresence.last_seen < cutoff_online).delete()
    db.session.commit()

    session_id = session.get("chat_sid")
    if not session_id:
        session_id = secrets.token_hex(16)
        session["chat_sid"] = session_id

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        body = sanitize_text(data.get("body") or "", max_len=1000)
        nickname = sanitize_text(data.get("nickname") or "", max_len=80)

        if has_malicious_input([body, nickname]):
            return jsonify({"ok": False, "error": "Contenido sospechoso."}), 400

        if not body:
            return jsonify({"ok": False, "error": "Mensaje vacío."}), 400

        nickname = _sanitize_nick(nickname, _get_chat_nick())
        session["chat_nick"] = nickname

        presence = ChatPresence.query.filter_by(session_id=session_id).first()
        if not presence:
            presence = ChatPresence(session_id=session_id, nickname=nickname, last_seen=now)
            db.session.add(presence)
        else:
            presence.nickname = nickname
            presence.last_seen = now

        author_id = current_user.id if current_user.is_authenticated else None
        msg = ChatMessage(author_id=author_id, author_label=nickname, body=body)
        db.session.add(msg)
        db.session.commit()
    else:
        nickname = _get_chat_nick()
        presence = ChatPresence.query.filter_by(session_id=session_id).first()
        if not presence:
            presence = ChatPresence(session_id=session_id, nickname=nickname, last_seen=now)
            db.session.add(presence)
        else:
            presence.last_seen = now
        db.session.commit()

    items = (
        ChatMessage.query.filter(ChatMessage.created_at >= cutoff_visible)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    online_count = ChatPresence.query.count()
    return jsonify(
        {
            "items": [
                {
                    "id": m.id,
                    "author": m.author_label,
                    "body": m.body,
                    "created_at": m.created_at.isoformat(),
                }
                for m in items
            ],
            "online_count": online_count,
        }
    )
