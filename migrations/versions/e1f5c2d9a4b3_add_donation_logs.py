"""add donation_logs

Revision ID: e1f5c2d9a4b3
Revises: d1a0c9d7b2f8
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1f5c2d9a4b3"
down_revision = "d1a0c9d7b2f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "donation_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount", sa.String(length=64), nullable=False),
        sa.Column("method", sa.String(length=120), nullable=False),
        sa.Column("donated_at", sa.Date(), nullable=False),
        sa.Column("destination", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("donation_logs")
