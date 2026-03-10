import pytest
from app.services.discussion_tags import upsert_tags, normalize_tag
from app.extensions import db


class TestUpsertTags:
    def test_creates_new_tags(self, app):
        with app.app_context():
            tags = upsert_tags(["Protesta", "Derechos"])
            assert len(tags) == 2
            assert tags[0].slug == "protesta"
            assert tags[1].slug == "derechos"

    def test_deduplicates(self, app):
        with app.app_context():
            upsert_tags(["Protesta"])
            tags = upsert_tags(["Protesta", "Nuevo"])
            assert len(tags) == 2
            # First tag reused, not duplicated
            from app.models.discussion_tag import DiscussionTag
            count = DiscussionTag.query.filter_by(slug="protesta").count()
            assert count == 1

    def test_skips_empty(self, app):
        with app.app_context():
            tags = upsert_tags(["", "  ", "Valid"])
            assert len(tags) == 1
            assert tags[0].slug == "valid"

    def test_truncates_long_names(self, app):
        with app.app_context():
            long_name = "a" * 200
            tags = upsert_tags([long_name])
            assert len(tags) == 1
            assert len(tags[0].slug) <= 80
