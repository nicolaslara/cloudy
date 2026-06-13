"""cloud rollups

Revision ID: 7c3a4a4b5c6d
Revises: 616b3e53d92a
Create Date: 2026-06-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c3a4a4b5c6d"
down_revision: str | Sequence[str] | None = "616b3e53d92a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_rollups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(length=8), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("expected_count", sa.Integer(), nullable=False),
        sa.Column("missing_count", sa.Integer(), nullable=False),
        sa.Column("mean_cloud_pct", sa.Float(), nullable=True),
        sa.Column("min_cloud_pct", sa.Float(), nullable=True),
        sa.Column("max_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p05_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p50_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p95_cloud_pct", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id",
            "source",
            "source_version",
            "resolution",
            "bucket_start",
            name="uq_cloud_rollup_station_resolution_start",
        ),
    )
    _backfill_rollups()
    op.create_index(
        op.f("ix_cloud_rollups_resolution"), "cloud_rollups", ["resolution"], unique=False
    )
    op.create_index(
        op.f("ix_cloud_rollups_station_id"), "cloud_rollups", ["station_id"], unique=False
    )
    op.create_index(
        "ix_cloud_rollups_station_resolution_start",
        "cloud_rollups",
        ["station_id", "resolution", "bucket_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_rollups_station_resolution_start", table_name="cloud_rollups")
    op.drop_index(op.f("ix_cloud_rollups_station_id"), table_name="cloud_rollups")
    op.drop_index(op.f("ix_cloud_rollups_resolution"), table_name="cloud_rollups")
    op.drop_table("cloud_rollups")


def _backfill_rollups() -> None:
    for resolution in ("hour", "6h", "day", "week", "month", "year"):
        op.execute(sa.text(_insert_rollup_sql(resolution)))


def _insert_rollup_sql(resolution: str) -> str:
    bucket_start = _bucket_start_expr(resolution)
    bucket_end = _bucket_end_expr(resolution, "bucket_start")
    return f"""
        INSERT INTO cloud_rollups (
            station_id,
            resolution,
            bucket_start,
            bucket_end,
            observed_count,
            expected_count,
            missing_count,
            mean_cloud_pct,
            min_cloud_pct,
            max_cloud_pct,
            p05_cloud_pct,
            p50_cloud_pct,
            p95_cloud_pct,
            source,
            source_version
        )
        WITH hourly AS (
            SELECT
                station_id,
                source,
                source_version,
                {bucket_start} AS bucket_start,
                cloud_pct
            FROM cloud_hourly
        ),
        bucketed AS (
            SELECT
                station_id,
                source,
                source_version,
                '{resolution}' AS resolution,
                bucket_start,
                {bucket_end} AS bucket_end,
                cloud_pct
            FROM hourly
        )
        SELECT
            station_id,
            resolution,
            bucket_start,
            bucket_end,
            count(cloud_pct)::int AS observed_count,
            (EXTRACT(EPOCH FROM (bucket_end - bucket_start)) / 3600.0)::int AS expected_count,
            GREATEST(
                ((EXTRACT(EPOCH FROM (bucket_end - bucket_start)) / 3600.0)::int)
                - count(cloud_pct)::int,
                0
            ) AS missing_count,
            avg(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS mean_cloud_pct,
            min(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS min_cloud_pct,
            max(cloud_pct) FILTER (WHERE cloud_pct IS NOT NULL) AS max_cloud_pct,
            percentile_cont(0.05) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p05_cloud_pct,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p50_cloud_pct,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY cloud_pct)
                FILTER (WHERE cloud_pct IS NOT NULL) AS p95_cloud_pct,
            source,
            source_version
        FROM bucketed
        GROUP BY station_id, resolution, bucket_start, bucket_end, source, source_version
        ORDER BY station_id, bucket_start
    """


def _bucket_start_expr(resolution: str) -> str:
    if resolution == "6h":
        return "date_bin(INTERVAL '6 hours', ts_utc, TIMESTAMPTZ '1970-01-01 00:00:00+00')"
    return f"date_trunc('{resolution}', ts_utc AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


def _bucket_end_expr(resolution: str, start_name: str) -> str:
    interval = {
        "hour": "1 hour",
        "6h": "6 hours",
        "day": "1 day",
        "week": "1 week",
        "month": "1 month",
        "year": "1 year",
    }[resolution]
    return f"{start_name} + INTERVAL '{interval}'"
