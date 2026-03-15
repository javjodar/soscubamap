"""add government and UJC categories

Revision ID: f2b7c4d9a8e1
Revises: e1f5c2d9a4b3
Create Date: 2026-03-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f2b7c4d9a8e1"
down_revision = "e1f5c2d9a4b3"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    new_categories = [
        {
            "name": "Sede del Gobierno",
            "slug": "sede-gobierno",
            "description": "Sedes provinciales o municipales del Gobierno.",
        },
        {
            "name": "Sede de la Unión de Jóvenes Comunistas",
            "slug": "sede-ujc",
            "description": "Sedes provinciales o municipales de la UJC.",
        },
    ]

    stmt = sa.text(
        """
        INSERT INTO categories (name, slug, description)
        SELECT :name, :slug, :description
        WHERE NOT EXISTS (
            SELECT 1 FROM categories WHERE slug = :slug_lookup
        )
        """
    )

    for category in new_categories:
        conn.execute(
            stmt,
            {
                **category,
                "slug_lookup": category["slug"],
            },
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM categories
            WHERE slug = :slug_government OR slug = :slug_ujc
            """
        ),
        {"slug_government": "sede-gobierno", "slug_ujc": "sede-ujc"},
    )
