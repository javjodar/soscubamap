"""add vote_records

Revision ID: d1a0c9d7b2f8
Revises: c2a4e7f9b1c0
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1a0c9d7b2f8"
down_revision = "c2a4e7f9b1c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vote_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("voter_hash", sa.String(length=64), nullable=False),
        sa.Column("value", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("target_type", "target_id", "voter_hash", name="uq_vote_record"),
    )
    op.create_index("ix_vote_records_target_type", "vote_records", ["target_type"], unique=False)
    op.create_index("ix_vote_records_target_id", "vote_records", ["target_id"], unique=False)
    op.create_index("ix_vote_records_voter_hash", "vote_records", ["voter_hash"], unique=False)


def downgrade():
    op.drop_index("ix_vote_records_voter_hash", table_name="vote_records")
    op.drop_index("ix_vote_records_target_id", table_name="vote_records")
    op.drop_index("ix_vote_records_target_type", table_name="vote_records")
    op.drop_table("vote_records")
