"""add connectivity tables

Revision ID: 7d9e2c4a1b3f
Revises: f2b7c4d9a8e1
Create Date: 2026-03-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d9e2c4a1b3f"
down_revision = "f2b7c4d9a8e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connectivity_ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scheduled_for_utc", sa.DateTime(), nullable=True),
        sa.Column("started_at_utc", sa.DateTime(), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_url", sa.String(length=1000), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_connectivity_ingestion_runs_scheduled_for_utc",
        "connectivity_ingestion_runs",
        ["scheduled_for_utc"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_ingestion_runs_started_at_utc",
        "connectivity_ingestion_runs",
        ["started_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_ingestion_runs_status",
        "connectivity_ingestion_runs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "connectivity_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ingestion_run_id",
            sa.Integer(),
            sa.ForeignKey("connectivity_ingestion_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("observed_at_utc", sa.DateTime(), nullable=False),
        sa.Column("fetched_at_utc", sa.DateTime(), nullable=False),
        sa.Column("traffic_value", sa.Float(), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("is_partial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("confidence", sa.String(length=32), nullable=False, server_default="country_level"),
        sa.Column("method", sa.String(length=64), nullable=False, server_default="national_replication_v1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_connectivity_snapshots_ingestion_run_id",
        "connectivity_snapshots",
        ["ingestion_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_snapshots_observed_at_utc",
        "connectivity_snapshots",
        ["observed_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_snapshots_fetched_at_utc",
        "connectivity_snapshots",
        ["fetched_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_snapshots_status",
        "connectivity_snapshots",
        ["status"],
        unique=False,
    )

    op.create_table(
        "connectivity_province_statuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer(),
            sa.ForeignKey("connectivity_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("province", sa.String(length=120), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "confidence",
            sa.String(length=32),
            nullable=False,
            server_default="estimated_country_level",
        ),
        sa.Column(
            "method",
            sa.String(length=64),
            nullable=False,
            server_default="national_replication_v1",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "province", name="uq_connectivity_snapshot_province"),
    )
    op.create_index(
        "ix_connectivity_province_statuses_snapshot_id",
        "connectivity_province_statuses",
        ["snapshot_id"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_province_statuses_province",
        "connectivity_province_statuses",
        ["province"],
        unique=False,
    )
    op.create_index(
        "ix_connectivity_province_statuses_status",
        "connectivity_province_statuses",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_connectivity_province_statuses_status",
        table_name="connectivity_province_statuses",
    )
    op.drop_index(
        "ix_connectivity_province_statuses_province",
        table_name="connectivity_province_statuses",
    )
    op.drop_index(
        "ix_connectivity_province_statuses_snapshot_id",
        table_name="connectivity_province_statuses",
    )
    op.drop_table("connectivity_province_statuses")

    op.drop_index("ix_connectivity_snapshots_status", table_name="connectivity_snapshots")
    op.drop_index(
        "ix_connectivity_snapshots_fetched_at_utc",
        table_name="connectivity_snapshots",
    )
    op.drop_index(
        "ix_connectivity_snapshots_observed_at_utc",
        table_name="connectivity_snapshots",
    )
    op.drop_index(
        "ix_connectivity_snapshots_ingestion_run_id",
        table_name="connectivity_snapshots",
    )
    op.drop_table("connectivity_snapshots")

    op.drop_index(
        "ix_connectivity_ingestion_runs_status",
        table_name="connectivity_ingestion_runs",
    )
    op.drop_index(
        "ix_connectivity_ingestion_runs_started_at_utc",
        table_name="connectivity_ingestion_runs",
    )
    op.drop_index(
        "ix_connectivity_ingestion_runs_scheduled_for_utc",
        table_name="connectivity_ingestion_runs",
    )
    op.drop_table("connectivity_ingestion_runs")
