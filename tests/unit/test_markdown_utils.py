from app.services.markdown_utils import render_markdown


class TestRenderMarkdown:
    def test_bold(self):
        result = render_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_emphasis(self):
        result = render_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_link(self):
        result = render_markdown("[click](https://example.com)")
        assert '<a href="https://example.com"' in result

    def test_plain_text(self):
        result = render_markdown("Just plain text")
        assert "Just plain text" in result

    def test_strips_disallowed_tags(self):
        result = render_markdown("<script>alert(1)</script>")
        assert "<script>" not in result
