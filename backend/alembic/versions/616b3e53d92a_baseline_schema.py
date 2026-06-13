"""baseline schema

Revision ID: 616b3e53d92a
Revises:
Create Date: 2026-06-11 20:57:23.253805

Tables created previously via create_all(); stamp head on existing DBs once.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "616b3e53d92a"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("job", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingest_runs_job"), "ingest_runs", ["job"], unique=False)
    op.create_table(
        "lightning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ts_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("peak_current_ka", sa.Float(), nullable=False),
        sa.Column("multiplicity", sa.Integer(), nullable=False),
        sa.Column("number_of_sensors", sa.Integer(), nullable=False),
        sa.Column("degrees_of_freedom", sa.Integer(), nullable=True),
        sa.Column("ellipse_angle", sa.Float(), nullable=True),
        sa.Column("semi_major_axis", sa.Float(), nullable=True),
        sa.Column("semi_minor_axis", sa.Float(), nullable=True),
        sa.Column("chi_square_value", sa.Float(), nullable=True),
        sa.Column("rise_time", sa.Float(), nullable=True),
        sa.Column("peak_to_zero_time", sa.Float(), nullable=True),
        sa.Column("max_rate_of_rise", sa.Float(), nullable=True),
        sa.Column("cloud_indicator", sa.Integer(), nullable=False),
        sa.Column("angle_indicator", sa.Integer(), nullable=True),
        sa.Column("signal_indicator", sa.Integer(), nullable=True),
        sa.Column("timing_indicator", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_lightning_events_day"), "lightning_events", ["day"], unique=False)
    op.create_index("ix_lightning_events_lat_lon", "lightning_events", ["lat", "lon"], unique=False)
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "cloud_hourly",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("ts_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cloud_pct", sa.Float(), nullable=True),
        sa.Column("quality", sa.String(length=1), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "station_id",
            "source",
            "source_version",
            "ts_utc",
            name="uq_cloud_hourly_station_ts",
        ),
    )
    op.create_index(
        op.f("ix_cloud_hourly_station_id"), "cloud_hourly", ["station_id"], unique=False
    )
    op.create_index(
        "ix_cloud_hourly_station_ts", "cloud_hourly", ["station_id", "ts_utc"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_cloud_hourly_station_ts", table_name="cloud_hourly")
    op.drop_index(op.f("ix_cloud_hourly_station_id"), table_name="cloud_hourly")
    op.drop_table("cloud_hourly")
    op.drop_table("stations")
    op.drop_index("ix_lightning_events_lat_lon", table_name="lightning_events")
    op.drop_index(op.f("ix_lightning_events_day"), table_name="lightning_events")
    op.drop_table("lightning_events")
    op.drop_index(op.f("ix_ingest_runs_job"), table_name="ingest_runs")
    op.drop_table("ingest_runs")
