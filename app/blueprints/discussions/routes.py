import json
import secrets
from flask import render_template, request, redirect, url_for, flash, session, current_app
from sqlalchemy import func
from flask_login import current_user

from app.extensions import db, limiter
from app.models.discussion_post import DiscussionPost
from app.models.discussion_comment import DiscussionComment
from app.models.discussion_tag import DiscussionTag
from app.services.markdown_utils import render_markdown
from app.services.discussion_tags import upsert_tags, normalize_tag
from app.services.media_upload import validate_files, upload_files, parse_media_json
from app.services.recaptcha import verify_recaptcha, recaptcha_enabled
from app.services.input_safety import has_malicious_input
from . import discussions_bp


def _get_discussion_nick():
    allow_admin = current_user.is_authenticated and current_user.has_role("administrador")
    nick = session.get("discussion_nick")
    if nick and (nick.lower() != "admin" or allow_admin):
        return nick
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "".join(secrets.choice(alphabet) for _ in range(4))
    nick = f"Anon-{code}"
    session["discussion_nick"] = nick
    return nick


def _resolve_discussion_nick(nickname: str) -> str:
    allow_admin = current_user.is_authenticated and current_user.has_role("administrador")
    value = (nickname or "").strip()
    if not value:
        value = _get_discussion_nick()
    if value.lower() == "admin" and not allow_admin:
        value = _get_discussion_nick()
    value = value[:80]
    session["discussion_nick"] = value
    return value


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


def _normalize_tag(value: str) -> str:
    return normalize_tag(value)


@discussions_bp.route("/discusiones", methods=["GET"])
def index():
    selected_tag = request.args.get("tag", "").strip().lower()
    if selected_tag:
        posts = (
            DiscussionPost.query.join(DiscussionPost.tags)
            .filter(DiscussionTag.slug == selected_tag)
            .order_by(DiscussionPost.created_at.desc())
            .all()
        )
    else:
        posts = DiscussionPost.query.order_by(DiscussionPost.created_at.desc()).all()
    for post in posts:
        post.rendered_body_html = post.body_html or render_markdown(post.body)
        images = parse_media_json(post.images_json)
        post.thumbnail_url = images[0]["url"] if images else None
    counts = dict(
        db.session.query(DiscussionComment.post_id, func.count(DiscussionComment.id))
        .group_by(DiscussionComment.post_id)
        .all()
    )
    tag_counts = (
        db.session.query(DiscussionTag, func.count(DiscussionPost.id))
        .join(DiscussionTag.posts)
        .group_by(DiscussionTag.id)
        .order_by(DiscussionTag.name.asc())
        .all()
    )
    return render_template(
        "discussions/index.html",
        posts=posts,
        comment_counts=counts,
        tag_counts=tag_counts,
        selected_tag=selected_tag,
        nick=_get_discussion_nick(),
    )


@discussions_bp.route("/discusiones/nueva", methods=["GET", "POST"])
@limiter.limit("3/minute; 30/day", methods=["POST"])
def new_discussion():
    if request.method == "POST":
        if recaptcha_enabled():
            token = request.form.get("g-recaptcha-response", "")
            if not verify_recaptcha(token, request.remote_addr):
                flash("Verificación reCAPTCHA falló. Intenta nuevamente.", "error")
                return redirect(url_for("discussions.new_discussion"))
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        nickname = request.form.get("nickname", "").strip()
        links_list = request.form.getlist("links[]")
        links_list = [link.strip() for link in links_list if link.strip()]
        selected_tags = request.form.getlist("tags[]")
        new_tags = request.form.get("new_tags", "")
        new_tags = [t.strip() for t in new_tags.split(",") if t.strip()]
        images = [
            file
            for file in request.files.getlist("images")
            if file and (file.filename or "").strip()
        ]
        image_captions = request.form.getlist("image_captions[]")

        if has_malicious_input([title, body, nickname] + links_list + selected_tags + new_tags):
            flash("Se detectó contenido sospechoso. Revisa y vuelve a intentar.", "error")
            return redirect(url_for("discussions.new_discussion"))

        if not title or not body:
            flash("Título y contenido son obligatorios.", "error")
            return redirect(url_for("discussions.new_discussion"))

        nickname = _resolve_discussion_nick(nickname)

        if images:
            ok, error = validate_files(images)
            if not ok:
                flash(error, "error")
                return redirect(url_for("discussions.new_discussion"))

        body_html = render_markdown(body)
        images_json = None
        if images:
            media_urls = upload_files(images)
            captions = _clean_captions(image_captions, len(media_urls))
            items = [
                {"url": url, "caption": (captions[idx] if idx < len(captions) else "")}
                for idx, url in enumerate(media_urls)
            ]
            images_json = json.dumps(items)

        post = DiscussionPost(
            title=title,
            body=body,
            body_html=body_html,
            links_json=json.dumps(links_list) if links_list else None,
            images_json=images_json,
            author_label=nickname,
        )
        tags = upsert_tags(selected_tags + new_tags)
        if tags:
            post.tags = tags
        db.session.add(post)
        db.session.commit()
        flash("Discusión publicada.", "success")
        return redirect(url_for("discussions.index"))

    tags = DiscussionTag.query.order_by(DiscussionTag.name.asc()).all()
    return render_template(
        "discussions/new.html",
        nick=_get_discussion_nick(),
        tags=tags,
        recaptcha_site_key=current_app.config.get("RECAPTCHA_V2_SITE_KEY"),
    )


@discussions_bp.route("/discusiones/<int:post_id>", methods=["GET", "POST"])
@limiter.limit("6/minute; 120/day", methods=["POST"])
def detail(post_id):
    post = DiscussionPost.query.get_or_404(post_id)

    if request.method == "POST":
        body = request.form.get("comment_body", "").strip()
        nickname = request.form.get("comment_nickname", "").strip()
        parent_id = request.form.get("parent_id", "").strip()
        if has_malicious_input([body, nickname]):
            flash("Se detectó contenido sospechoso. Revisa y vuelve a intentar.", "error")
            return redirect(url_for("discussions.detail", post_id=post.id))
        if not body:
            flash("El comentario no puede estar vacío.", "error")
            return redirect(url_for("discussions.detail", post_id=post.id))

        nickname = _resolve_discussion_nick(nickname)

        parent = None
        if parent_id:
            try:
                parent_id_int = int(parent_id)
                parent = DiscussionComment.query.filter_by(id=parent_id_int, post_id=post.id).first()
            except Exception:
                parent = None

        comment = DiscussionComment(
            post_id=post.id,
            body=body,
            body_html=render_markdown(body),
            author_label=nickname,
            parent_id=parent.id if parent else None,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Comentario agregado.", "success")
        return redirect(url_for("discussions.detail", post_id=post.id))

    links = []
    if post.links_json:
        try:
            links = json.loads(post.links_json)
        except Exception:
            links = []

    images = parse_media_json(post.images_json)
    comments = DiscussionComment.query.filter_by(post_id=post.id).order_by(DiscussionComment.created_at.asc()).all()
    comment_map = {c.id: c for c in comments}
    roots = []
    for comment in comments:
        comment.thread_children = []
        comment.rendered_body_html = comment.body_html or render_markdown(comment.body)
    for comment in comments:
        if comment.parent_id and comment.parent_id in comment_map:
            comment_map[comment.parent_id].thread_children.append(comment)
        else:
            roots.append(comment)
    post_rendered = post.body_html or render_markdown(post.body)
    return render_template(
        "discussions/detail.html",
        post=post,
        post_rendered=post_rendered,
        links=links,
        images=images,
        tags=post.tags,
        comments=roots,
        nick=_get_discussion_nick(),
    )
