from app.services.text_sanitize import sanitize_text


class TestSanitizeText:
    def test_strips_html_tags(self):
        assert sanitize_text("<b>bold</b> <i>italic</i>") == "bold italic"

    def test_strips_attributes(self):
        result = sanitize_text('<a href="evil.com">click</a>')
        assert "href" not in result
        assert "click" in result

    def test_respects_max_len(self):
        result = sanitize_text("abcdefghij", max_len=5)
        assert result == "abcde"

    def test_empty_string(self):
        assert sanitize_text("") == ""

    def test_none_value(self):
        assert sanitize_text(None) == ""

    def test_clean_text_unchanged(self):
        text = "Texto limpio sin HTML"
        assert sanitize_text(text) == text
