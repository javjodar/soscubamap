from unittest.mock import MagicMock
from app.services.vote_identity import get_voter_hash


def _make_user(authenticated=True, user_id=42):
    user = MagicMock()
    user.is_authenticated = authenticated
    user.id = user_id
    return user


def _make_request(ip="1.2.3.4", ua="TestAgent", cf_ip=None):
    req = MagicMock()
    headers = {"User-Agent": ua}
    if cf_ip:
        headers["CF-Connecting-IP"] = cf_ip
    req.headers = headers
    req.remote_addr = ip
    return req


class TestGetVoterHash:
    def test_authenticated_user(self):
        user = _make_user(authenticated=True, user_id=7)
        request = _make_request()
        h = get_voter_hash(user, request, "secret")
        assert isinstance(h, str) and len(h) == 64

    def test_anonymous_user(self):
        user = _make_user(authenticated=False)
        request = _make_request(ip="10.0.0.1", ua="Mozilla/5.0")
        h = get_voter_hash(user, request, "secret")
        assert isinstance(h, str) and len(h) == 64

    def test_cf_ip_takes_priority(self):
        user = _make_user(authenticated=False)
        req_cf = _make_request(ip="10.0.0.1", ua="Bot", cf_ip="99.99.99.99")
        req_no = _make_request(ip="10.0.0.1", ua="Bot")
        h_cf = get_voter_hash(user, req_cf, "secret")
        h_no = get_voter_hash(user, req_no, "secret")
        assert h_cf != h_no

    def test_deterministic(self):
        user = _make_user(authenticated=True, user_id=5)
        request = _make_request()
        h1 = get_voter_hash(user, request, "secret")
        h2 = get_voter_hash(user, request, "secret")
        assert h1 == h2
