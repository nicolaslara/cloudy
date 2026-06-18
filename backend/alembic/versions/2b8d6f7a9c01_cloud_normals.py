"""cloud normals

Revision ID: 2b8d6f7a9c01
Revises: 91f2c3d4e5f6
Create Date: 2026-06-16 17:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2b8d6f7a9c01"
down_revision: str | Sequence[str] | None = "91f2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cloud_normals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=8), nullable=False),
        sa.Column("bucket", sa.Integer(), nullable=False),
        sa.Column("mean_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p10_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p50_cloud_pct", sa.Float(), nullable=True),
        sa.Column("p90_cloud_pct", sa.Float(), nullable=True),
        sa.Column("clear_pct", sa.Float(), nullable=True),
        sa.Column("partial_pct", sa.Float(), nullable=True),
        sa.Column("overcast_pct", sa.Float(), nullable=True),
        sa.Column("observed_count", sa.Integer(), nullable=False),
        sa.Column("year_count", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "source_version",
            "period",
            "bucket",
            name="uq_cloud_normals_source_period_bucket",
        ),
    )
    _backfill_normals()
    op.create_index("ix_cloud_normals_period", "cloud_normals", ["period"], unique=False)
    op.create_index(
        "ix_cloud_normals_period_bucket",
        "cloud_normals",
        ["period", "bucket"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_normals_period_bucket", table_name="cloud_normals")
    op.drop_index("ix_cloud_normals_period", table_name="cloud_normals")
    op.drop_table("cloud_normals")


def _backfill_normals() -> None:
    for period, field in (("day", "doy"), ("month", "month"), ("year", "year")):
        op.execute(sa.text(_insert_normal_sql(period, field)))


def _insert_normal_sql(period: str, field: str) -> str:
    bucket = f"EXTRACT({field} FROM ts_utc)::int"
    return f"""
        INSERT INTO cloud_normals (
            period,
            bucket,
            mean_cloud_pct,
            p10_cloud_pct,
            p50_cloud_pct,
            p90_cloud_pct,
            clear_pct,
            partial_pct,
            overcast_pct,
            observed_count,
            year_count,
            source,
            source_version,
            generated_at
        )
        SELECT
            '{period}' AS period,
            {bucket} AS bucket,
            avg(cloud_pct) AS mean_cloud_pct,
            percentile_cont(0.10) WITHIN GROUP (ORDER BY cloud_pct) AS p10_cloud_pct,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY cloud_pct) AS p50_cloud_pct,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY cloud_pct) AS p90_cloud_pct,
            100.0 * count(*) FILTER (WHERE cloud_pct < 25)
                / NULLIF(count(cloud_pct), 0) AS clear_pct,
            100.0 * count(*) FILTER (WHERE cloud_pct >= 25 AND cloud_pct <= 75)
                / NULLIF(count(cloud_pct), 0) AS partial_pct,
            100.0 * count(*) FILTER (WHERE cloud_pct > 75)
                / NULLIF(count(cloud_pct), 0) AS overcast_pct,
            count(cloud_pct)::int AS observed_count,
            count(DISTINCT EXTRACT(YEAR FROM ts_utc))::int AS year_count,
            source,
            source_version,
            now() AS generated_at
        FROM cloud_hourly
        WHERE station_id IN (SELECT id FROM stations WHERE active)
        GROUP BY source, source_version, {bucket}
        ORDER BY source, source_version, bucket
    """
