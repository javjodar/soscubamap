import pytest
from unittest.mock import patch, MagicMock
from app.services.authz import role_required


class TestRoleRequired:
    def test_unauthenticated_aborts_401(self, app):
        with app.app_context():
            @role_required("admin")
            def protected():
                return "ok"

            with app.test_request_context():
                with patch("app.services.authz.current_user") as mock_user:
                    mock_user.is_authenticated = False
                    with pytest.raises(Exception) as exc_info:
                        protected()
                    assert exc_info.value.code == 401

    def test_wrong_role_aborts_403(self, app):
        with app.app_context():
            @role_required("admin")
            def protected():
                return "ok"

            with app.test_request_context():
                mock_user = MagicMock()
                mock_user.is_authenticated = True
                mock_user.has_role = lambda r: False
                with patch("app.services.authz.current_user", mock_user):
                    with pytest.raises(Exception) as exc_info:
                        protected()
                    assert exc_info.value.code == 403

    def test_correct_role_passes(self, app):
        with app.app_context():
            @role_required("admin")
            def protected():
                return "ok"

            with app.test_request_context():
                mock_user = MagicMock()
                mock_user.is_authenticated = True
                mock_user.has_role = lambda r: True
                with patch("app.services.authz.current_user", mock_user):
                    result = protected()
                    assert result == "ok"
