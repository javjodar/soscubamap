import io
import json
import pytest
from unittest.mock import MagicMock, patch
from app.services.media_upload import (
    parse_media_json,
    get_media_payload,
    get_media_urls,
    media_json_from_post,
    validate_files,
    upload_files,
)


class TestParseMediaJson:
    def test_empty(self):
        assert parse_media_json("") == []
        assert parse_media_json(None) == []

    def test_invalid_json(self):
        assert parse_media_json("not json") == []

    def test_list_of_strings(self):
        raw = json.dumps(["http://img1.jpg", "http://img2.jpg"])
        result = parse_media_json(raw)
        assert len(result) == 2
        assert result[0] == {"url": "http://img1.jpg", "caption": ""}

    def test_list_of_dicts(self):
        raw = json.dumps([{"url": "http://img.jpg", "caption": "foto"}])
        result = parse_media_json(raw)
        assert result == [{"url": "http://img.jpg", "caption": "foto"}]

    def test_dict_with_file_url(self):
        raw = json.dumps([{"file_url": "http://img.jpg"}])
        result = parse_media_json(raw)
        assert result[0]["url"] == "http://img.jpg"

    def test_skips_empty_url(self):
        raw = json.dumps([{"url": ""}, {"url": "http://ok.jpg"}])
        result = parse_media_json(raw)
        assert len(result) == 1

    def test_skips_empty_strings(self):
        raw = json.dumps(["", "http://ok.jpg"])
        result = parse_media_json(raw)
        assert len(result) == 1


class TestGetMediaPayload:
    def test_with_media(self):
        media1 = MagicMock(file_url="http://img1.jpg", caption="foto1")
        media2 = MagicMock(file_url="http://img2.jpg", caption=None)
        post = MagicMock(media=[media1, media2])
        result = get_media_payload(post)
        assert len(result) == 2
        assert result[0] == {"url": "http://img1.jpg", "caption": "foto1"}
        assert result[1]["caption"] == ""

    def test_skips_no_url(self):
        media = MagicMock(file_url="", caption="x")
        post = MagicMock(media=[media])
        assert get_media_payload(post) == []

    def test_empty_media(self):
        post = MagicMock(media=[])
        assert get_media_payload(post) == []


class TestGetMediaUrls:
    def test_returns_urls(self):
        media = MagicMock(file_url="http://img.jpg", caption="")
        post = MagicMock(media=[media])
        assert get_media_urls(post) == ["http://img.jpg"]


class TestMediaJsonFromPost:
    def test_serializes(self):
        media = MagicMock(file_url="http://img.jpg", caption="test")
        post = MagicMock(media=[media])
        raw = media_json_from_post(post)
        data = json.loads(raw)
        assert data == [{"url": "http://img.jpg", "caption": "test"}]


def _make_file(name="test.jpg", content=b"fake", size=None):
    f = MagicMock()
    f.filename = name
    stream = io.BytesIO(content if size is None else b"x" * size)
    f.stream = stream
    return f


class TestValidateFiles:
    def test_empty_list(self, app):
        with app.app_context():
            ok, msg = validate_files([])
            assert ok is True

    def test_valid_file(self, app):
        with app.app_context():
            ok, msg = validate_files([_make_file("photo.jpg")])
            assert ok is True

    def test_too_many_files(self, app):
        with app.app_context():
            files = [_make_file(f"img{i}.jpg") for i in range(10)]
            ok, msg = validate_files(files)
            assert ok is False
            assert "Máximo" in msg

    def test_invalid_extension(self, app):
        with app.app_context():
            ok, msg = validate_files([_make_file("virus.exe")])
            assert ok is False
            assert "Formato" in msg

    def test_file_too_large(self, app):
        with app.app_context():
            ok, msg = validate_files([_make_file("big.jpg", size=10 * 1024 * 1024)])
            assert ok is False
            assert "MB" in msg

    def test_no_filename(self, app):
        with app.app_context():
            f = _make_file("")
            # secure_filename("") returns "" → invalid
            ok, msg = validate_files([f])
            # Empty filename file is filtered out in the first line
            assert ok is True


class TestUploadFiles:
    @patch("app.services.media_upload.cloudinary.uploader.upload")
    @patch("app.services.media_upload._cloudinary_config")
    def test_upload(self, mock_config, mock_upload, app):
        with app.app_context():
            mock_upload.return_value = {"secure_url": "https://cdn/img.jpg"}
            f = _make_file("photo.jpg")
            urls = upload_files([f])
            assert urls == ["https://cdn/img.jpg"]
            mock_upload.assert_called_once()
