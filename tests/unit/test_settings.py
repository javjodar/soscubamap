import pytest
from app.services.settings import get_setting, set_setting


class TestSettings:
    def test_get_default(self, app):
        with app.app_context():
            assert get_setting("nonexistent", "fallback") == "fallback"

    def test_set_and_get(self, app):
        with app.app_context():
            set_setting("site_name", "SOSCuba")
            assert get_setting("site_name") == "SOSCuba"

    def test_update_existing(self, app):
        with app.app_context():
            set_setting("key1", "value1")
            set_setting("key1", "value2")
            assert get_setting("key1") == "value2"

    def test_get_none_default(self, app):
        with app.app_context():
            assert get_setting("missing") is None
