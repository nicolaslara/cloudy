"""lightning daily rollups

Revision ID: 91f2c3d4e5f6
Revises: 7c3a4a4b5c6d
Create Date: 2026-06-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "91f2c3d4e5f6"
down_revision: str | Sequence[str] | None = "7c3a4a4b5c6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lightning_daily_rollups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cg_count", sa.Integer(), nullable=False),
        sa.Column("all_count", sa.Integer(), nullable=False),
        sa.Column("lightning_days", sa.Integer(), nullable=False),
        sa.Column("max_abs_peak_ka", sa.Float(), nullable=True),
        sa.Column("strongest_event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "source_version",
            "day",
            name="uq_lightning_daily_rollup_source_day",
        ),
    )
    op.execute(sa.text(_backfill_sql()))
    op.create_index(
        "ix_lightning_daily_rollups_day",
        "lightning_daily_rollups",
        ["day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_lightning_daily_rollups_day", table_name="lightning_daily_rollups")
    op.drop_table("lightning_daily_rollups")


def _backfill_sql() -> str:
    return """
        INSERT INTO lightning_daily_rollups (
            day,
            bucket_start,
            bucket_end,
            cg_count,
            all_count,
            lightning_days,
            max_abs_peak_ka,
            strongest_event_time,
            source,
            source_version
        )
        SELECT
            day,
            day::timestamp AT TIME ZONE 'UTC' AS bucket_start,
            (day + 1)::timestamp AT TIME ZONE 'UTC' AS bucket_end,
            count(*) FILTER (WHERE cloud_indicator = 0)::int AS cg_count,
            count(*)::int AS all_count,
            1 AS lightning_days,
            max(abs(peak_current_ka)) AS max_abs_peak_ka,
            (array_agg(ts_utc ORDER BY abs(peak_current_ka) DESC, ts_utc))[1]
                AS strongest_event_time,
            source,
            source_version
        FROM lightning_events
        GROUP BY day, source, source_version
        ORDER BY day
    """
