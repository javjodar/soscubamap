import json
import secrets
from flask import render_template, request, redirect, url_for, flash, session
from sqlalchemy import func

from app.extensions import db
from app.models.discussion_post import DiscussionPost
from app.models.discussion_comment import DiscussionComment
from app.services.markdown_utils import render_markdown
from app.services.media_upload import validate_files, upload_files, parse_media_json
from . import discussions_bp


def _get_discussion_nick():
    nick = session.get("discussion_nick")
    if nick:
        return nick
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "".join(secrets.choice(alphabet) for _ in range(4))
    nick = f"Anon-{code}"
    session["discussion_nick"] = nick
    return nick


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


@discussions_bp.route("/discusiones", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        nickname = request.form.get("nickname", "").strip()
        links_list = request.form.getlist("links[]")
        links_list = [link.strip() for link in links_list if link.strip()]
        images = [
            file
            for file in request.files.getlist("images")
            if file and (file.filename or "").strip()
        ]
        image_captions = request.form.getlist("image_captions[]")

        if not title or not body:
            flash("Título y contenido son obligatorios.", "error")
            return redirect(url_for("discussions.index"))

        if not nickname:
            nickname = _get_discussion_nick()
        nickname = nickname[:80]
        session["discussion_nick"] = nickname

        if images:
            ok, error = validate_files(images)
            if not ok:
                flash(error, "error")
                return redirect(url_for("discussions.index"))

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
        db.session.add(post)
        db.session.commit()
        flash("Discusión publicada.", "success")
        return redirect(url_for("discussions.detail", post_id=post.id))

    posts = DiscussionPost.query.order_by(DiscussionPost.created_at.desc()).all()
    counts = dict(
        db.session.query(DiscussionComment.post_id, func.count(DiscussionComment.id))
        .group_by(DiscussionComment.post_id)
        .all()
    )
    return render_template(
        "discussions/index.html",
        posts=posts,
        comment_counts=counts,
        nick=_get_discussion_nick(),
    )


@discussions_bp.route("/discusiones/<int:post_id>", methods=["GET", "POST"])
def detail(post_id):
    post = DiscussionPost.query.get_or_404(post_id)

    if request.method == "POST":
        body = request.form.get("comment_body", "").strip()
        nickname = request.form.get("comment_nickname", "").strip()
        if not body:
            flash("El comentario no puede estar vacío.", "error")
            return redirect(url_for("discussions.detail", post_id=post.id))

        if not nickname:
            nickname = _get_discussion_nick()
        nickname = nickname[:80]
        session["discussion_nick"] = nickname

        comment = DiscussionComment(
            post_id=post.id,
            body=body,
            body_html=render_markdown(body),
            author_label=nickname,
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
    return render_template(
        "discussions/detail.html",
        post=post,
        links=links,
        images=images,
        comments=comments,
        nick=_get_discussion_nick(),
    )
