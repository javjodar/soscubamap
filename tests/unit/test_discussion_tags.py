from app.services.discussion_tags import normalize_tag


class TestNormalizeTag:
    def test_normalizes_spaces_and_lowercase(self):
        assert normalize_tag("  Mi  Tag  ") == "mi tag"

    def test_empty_string(self):
        assert normalize_tag("") == ""

    def test_whitespace_only(self):
        assert normalize_tag("   ") == ""

    def test_preserves_accents(self):
        assert normalize_tag("Información Pública") == "información pública"
