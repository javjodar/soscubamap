from flask import jsonify, request, make_response, session
import json
import secrets
from datetime import datetime, timedelta
from flask_login import current_user

from app.extensions import db
from app.models.comment import Comment
from app.models.user import User
from app.models.role import Role
from app.models.media import Media
from app.models.post_revision import PostRevision
from app.models.post_edit_request import PostEditRequest
from app.models.site_setting import SiteSetting
from app.services.media_upload import validate_files, upload_files, media_json_from_post, get_media_urls
from app.models.chat_message import ChatMessage
from app.models.chat_presence import ChatPresence

from app.models.post import Post
from app.models.category import Category
from . import api_bp


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
    query = Post.query.filter_by(status="approved")
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
                "created_at": p.created_at.isoformat(),
                "anon": f"Anon-{p.author.anon_code}" if p.author and p.author.anon_code else "Anon",
                "polygon_geojson": p.polygon_geojson,
                "links": json.loads(p.links_json) if p.links_json else [],
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
def comments(post_id):
    post = Post.query.get_or_404(post_id)
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        body = (data.get("body") or "").strip()
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
def vote_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    data = request.get_json(silent=True) or {}
    value = data.get("value")
    if value not in (1, -1):
        return jsonify({"ok": False, "error": "Voto inválido."}), 400

    cookie_key = f"comment_vote_{comment_id}"
    if request.cookies.get(cookie_key):
        return jsonify(
            {
                "ok": False,
                "upvotes": comment.upvotes or 0,
                "downvotes": comment.downvotes or 0,
                "score": (comment.upvotes or 0) - (comment.downvotes or 0),
            }
        )

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
    resp.set_cookie(cookie_key, "1")
    return resp


@api_bp.route("/posts/<int:post_id>/media", methods=["POST"])
def upload_post_media(post_id):
    post = Post.query.get_or_404(post_id)
    files = request.files.getlist("images")
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
        combined = get_media_urls(post) + urls
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
        category_id=post.category_id,
        polygon_geojson=post.polygon_geojson,
        links_json=post.links_json,
        media_json=media_json_from_post(post),
    )
    db.session.add(revision)

    for url in urls:
        db.session.add(Media(post_id=post.id, file_url=url))
    db.session.commit()

    return jsonify({"ok": True, "status": "approved", "media": get_media_urls(post)})


@api_bp.route("/chat", methods=["GET", "POST"])
def chat_messages():
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
        body = (data.get("body") or "").strip()
        nickname = (data.get("nickname") or "").strip()

        if not body:
            return jsonify({"ok": False, "error": "Mensaje vacío."}), 400

        if not nickname:
            nickname = session.get("chat_nick") or "Anon"

        nickname = nickname[:80]
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
        nickname = session.get("chat_nick") or "Anon"
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
