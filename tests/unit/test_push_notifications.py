import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


class TestPushEnabled:
    def test_enabled(self, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = "pub"
            app.config["VAPID_PRIVATE_KEY"] = "priv"
            from app.services.push_notifications import push_enabled
            assert push_enabled() is True

    def test_disabled_no_keys(self, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = ""
            app.config["VAPID_PRIVATE_KEY"] = ""
            from app.services.push_notifications import push_enabled
            assert push_enabled() is False


class TestFormatAlertPayload:
    def test_format(self, app):
        with app.app_context():
            from app.services.push_notifications import _format_alert_payload
            cat = MagicMock(name="Acción represiva")
            # MagicMock overrides .name, need to set explicitly
            cat.name = "Acción represiva"
            post = MagicMock(
                id=42,
                title="Detención arbitraria",
                province="La Habana",
                municipality="Playa",
                movement_at=datetime(2024, 1, 15, 10, 30),
                created_at=datetime(2024, 1, 15, 10, 0),
                category=cat,
            )
            payload = _format_alert_payload(post)
            assert "Acción represiva" in payload["title"]
            assert "Detención" in payload["body"]
            assert payload["tag"] == "alert-42"
            assert payload["icon"] == "/static/img/favico.png"

    def test_no_category(self, app):
        with app.app_context():
            from app.services.push_notifications import _format_alert_payload
            post = MagicMock(
                id=1,
                title="Test",
                province=None,
                municipality=None,
                movement_at=None,
                created_at=None,
                category=None,
            )
            payload = _format_alert_payload(post)
            assert "Alerta" in payload["title"]


class TestSendAlertNotification:
    @patch("app.services.push_notifications.PushSubscription")
    @patch("app.services.push_notifications.webpush")
    def test_sends_to_subscriptions(self, mock_webpush, mock_model, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = "pub"
            app.config["VAPID_PRIVATE_KEY"] = "priv"
            sub = MagicMock(endpoint="https://push/1", p256dh="key", auth="auth", active=True)
            mock_model.query.filter_by.return_value.all.return_value = [sub]

            cat = MagicMock()
            cat.name = "Alerta"
            post = MagicMock(
                id=1, title="Test", province=None, municipality=None,
                movement_at=None, created_at=None, category=cat,
            )
            from app.services.push_notifications import send_alert_notification
            count = send_alert_notification(post)
            assert count == 1
            mock_webpush.assert_called_once()

    @patch("app.services.push_notifications.PushSubscription")
    @patch("app.services.push_notifications.webpush")
    def test_marks_stale_on_410(self, mock_webpush, mock_model, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = "pub"
            app.config["VAPID_PRIVATE_KEY"] = "priv"
            sub = MagicMock(endpoint="https://push/1", p256dh="k", auth="a", active=True)
            mock_model.query.filter_by.return_value.all.return_value = [sub]

            from app.services.push_notifications import WebPushException
            resp = MagicMock(status_code=410)
            mock_webpush.side_effect = WebPushException("gone", response=resp)

            cat = MagicMock()
            cat.name = "Test"
            post = MagicMock(
                id=1, title="T", province=None, municipality=None,
                movement_at=None, created_at=None, category=cat,
            )
            from app.services.push_notifications import send_alert_notification
            count = send_alert_notification(post)
            assert count == 0
            assert sub.active is False

    def test_disabled_returns_zero(self, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = ""
            from app.services.push_notifications import send_alert_notification
            post = MagicMock()
            assert send_alert_notification(post) == 0

    @patch("app.services.push_notifications.PushSubscription")
    def test_no_subscriptions(self, mock_model, app):
        with app.app_context():
            app.config["VAPID_PUBLIC_KEY"] = "pub"
            app.config["VAPID_PRIVATE_KEY"] = "priv"
            mock_model.query.filter_by.return_value.all.return_value = []
            from app.services.push_notifications import send_alert_notification
            post = MagicMock()
            assert send_alert_notification(post) == 0
