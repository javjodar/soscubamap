import json
import pytest
from unittest.mock import patch, MagicMock
from app.services.recaptcha import recaptcha_enabled, verify_recaptcha


class TestRecaptchaEnabled:
    def test_enabled(self, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            assert recaptcha_enabled() is True

    def test_disabled(self, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = ""
            assert recaptcha_enabled() is False


class TestVerifyRecaptcha:
    def test_no_secret_returns_true(self, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = ""
            assert verify_recaptcha("token") is True

    def test_no_token_returns_false(self, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            assert verify_recaptcha("") is False

    @patch("app.services.recaptcha.urllib.request.urlopen")
    def test_success(self, mock_urlopen, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            resp = MagicMock()
            resp.read.return_value = json.dumps({"success": True}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = resp
            assert verify_recaptcha("valid-token") is True

    @patch("app.services.recaptcha.urllib.request.urlopen")
    def test_failure(self, mock_urlopen, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            resp = MagicMock()
            resp.read.return_value = json.dumps({"success": False}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = resp
            assert verify_recaptcha("bad-token") is False

    @patch("app.services.recaptcha.urllib.request.urlopen")
    def test_with_remote_ip(self, mock_urlopen, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            resp = MagicMock()
            resp.read.return_value = json.dumps({"success": True}).encode()
            resp.__enter__ = lambda s: s
            resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = resp
            assert verify_recaptcha("token", remote_ip="1.2.3.4") is True

    @patch("app.services.recaptcha.urllib.request.urlopen")
    def test_network_error(self, mock_urlopen, app):
        with app.app_context():
            app.config["RECAPTCHA_V2_SECRET_KEY"] = "secret"
            mock_urlopen.side_effect = Exception("timeout")
            assert verify_recaptcha("token") is False
