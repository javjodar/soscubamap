import os
import json
from typing import List, Tuple

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
    if not files:
        return False, "No se recibieron imágenes."

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
    for file in files:
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


def get_media_urls(post) -> List[str]:
    return [m.file_url for m in (post.media or []) if m.file_url]


def media_json_from_post(post) -> str:
    return json.dumps(get_media_urls(post))
