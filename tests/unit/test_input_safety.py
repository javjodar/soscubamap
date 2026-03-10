import pytest
from app.services.input_safety import is_malicious, has_malicious_input


class TestIsMalicious:
    def test_script_tag(self):
        assert is_malicious("<script>alert(1)</script>") is True

    def test_iframe_tag(self):
        assert is_malicious('<iframe src="evil.com">') is True

    def test_svg_tag(self):
        assert is_malicious("<svg onload=alert(1)>") is True

    def test_javascript_protocol(self):
        assert is_malicious("javascript:alert(1)") is True

    def test_inline_handler(self):
        assert is_malicious('onerror=alert(1)') is True

    def test_union_select(self):
        assert is_malicious("1 UNION SELECT * FROM users") is True

    def test_drop_table(self):
        assert is_malicious("'; DROP TABLE users; --") is True

    def test_insert_into(self):
        assert is_malicious("INSERT INTO users VALUES (1)") is True

    def test_update_set(self):
        assert is_malicious("UPDATE users SET admin=1") is True

    def test_sleep_injection(self):
        assert is_malicious("pg_sleep(5)") is True
        assert is_malicious("sleep(5)") is True

    def test_benchmark(self):
        assert is_malicious("benchmark(1000000,SHA1('test'))") is True

    def test_rce_patterns(self):
        assert is_malicious("curl http://evil.com") is True
        assert is_malicious("wget http://evil.com") is True
        assert is_malicious("ping -c 1 evil.com") is True

    def test_template_injection(self):
        assert is_malicious("${7*7}") is True
        assert is_malicious("{{config}}") is True
        assert is_malicious("<%=system('id')%>") is True

    def test_path_traversal(self):
        assert is_malicious("/etc/passwd") is True
        assert is_malicious("c:\\windows\\system32") is True

    def test_null_bytes(self):
        assert is_malicious("file%00.php") is True

    def test_bxss(self):
        assert is_malicious("https://bxss.me/t") is True

    def test_clean_spanish_text(self):
        assert is_malicious("Detención arbitraria en La Habana Vieja") is False

    def test_empty_and_none(self):
        assert is_malicious("") is False
        assert is_malicious(None) is False


class TestHasMaliciousInput:
    def test_mixed_list(self):
        values = ["texto normal", "<script>alert(1)</script>", "otro texto"]
        assert has_malicious_input(values) is True

    def test_all_clean(self):
        assert has_malicious_input(["hola", "mundo", "normal"]) is False

    def test_none_values_skipped(self):
        assert has_malicious_input([None, "", "texto limpio"]) is False
