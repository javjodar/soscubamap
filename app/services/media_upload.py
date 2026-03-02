import os
import json
from typing import List, Tuple, Dict, Any

import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename

from flask import current_app


def _cloudinary_config():
    cloudinary.config(
        cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
        api_key=current_app.config.get("CLOUDINARY_API_KEY"),
        api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def _allowed_extensions():
    raw = current_app.config.get("IMAGE_ALLOWED_EXTENSIONS", "jpg,jpeg,png,webp,heic")
    return {ext.strip().lower() for ext in raw.split(",") if ext.strip()}


def _max_bytes():
    mb = current_app.config.get("IMAGE_MAX_MB", 2)
    return int(mb) * 1024 * 1024


def _max_count():
    return int(current_app.config.get("IMAGE_MAX_PER_SUBMIT", 3))


def validate_files(files) -> Tuple[bool, str]:
    files = [file for file in (files or []) if file and (file.filename or "").strip()]
    if not files:
        return True, ""

    if len(files) > _max_count():
        return False, f"Máximo {_max_count()} imágenes por envío."

    allowed = _allowed_extensions()
    max_bytes = _max_bytes()

    for file in files:
        filename = secure_filename(file.filename or "")
        if not filename:
            return False, "Archivo inválido."

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in allowed:
            return False, f"Formato no permitido: {ext or 'desconocido'}."

        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > max_bytes:
            return False, f"Cada imagen debe ser <= {current_app.config.get('IMAGE_MAX_MB', 2)}MB."

    return True, ""


def upload_files(files) -> List[str]:
    _cloudinary_config()
    urls = []
    for file in (files or []):
        if not file or not (file.filename or "").strip():
            continue
        filename = secure_filename(file.filename or "imagen")
        result = cloudinary.uploader.upload(
            file,
            folder="soscubamap",
            public_id=None,
            resource_type="image",
            filename_override=filename,
        )
        url = result.get("secure_url") or result.get("url")
        if url:
            urls.append(url)
    return urls


def get_media_payload(post) -> List[Dict[str, Any]]:
    items = []
    for media in (post.media or []):
        if not media.file_url:
            continue
        items.append(
            {
                "url": media.file_url,
                "caption": media.caption or "",
            }
        )
    return items


def get_media_urls(post) -> List[str]:
    return [item["url"] for item in get_media_payload(post) if item.get("url")]


def media_json_from_post(post) -> str:
    return json.dumps(get_media_payload(post))


def parse_media_json(raw: str) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw) or []
    except Exception:
        return []

    items = []
    for item in data:
        if isinstance(item, str):
            if item:
                items.append({"url": item, "caption": ""})
            continue
        if isinstance(item, dict):
            url = item.get("url") or item.get("file_url") or ""
            if not url:
                continue
            caption = item.get("caption") or ""
            items.append({"url": url, "caption": caption})
    return items
