"""add movement_at to posts and edit tables

Revision ID: b7c1a8f0b2de
Revises: 5f3c2a8d6c1b
Create Date: 2026-03-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c1a8f0b2de"
down_revision = "5f3c2a8d6c1b"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("movement_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("post_edit_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("movement_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("movement_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.drop_column("movement_at")

    with op.batch_alter_table("post_edit_requests", schema=None) as batch_op:
        batch_op.drop_column("movement_at")

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.drop_column("movement_at")
