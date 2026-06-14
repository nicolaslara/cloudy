"""SQLModel tables for cloudy.

Every observation/rollup row carries (source, source_version) and they are part
of each natural-key UniqueConstraint: that's what lets us re-ingest one source
version idempotently and keep distinct sources side by side without mixing them
in a single chart. Timestamp columns are all timezone-aware (UTC); see the
data-modeling rules in AGENTS.md.
"""

from datetime import date, datetime

from sqlalchemy import Column, DateTime, Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class IngestRun(SQLModel, table=True):
    """One ingestion job run: resumable watermark + freshness feed for /health."""

    __tablename__ = "ingest_runs"

    id: int | None = Field(default=None, primary_key=True)
    source: str = Field(max_length=64)
    job: str = Field(max_length=64, index=True)
    started_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    finished_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    status: str = Field(max_length=16)
    detail: str | None = None


class LightningEvent(SQLModel, table=True):
    """One discharge from the SMHI lightning archive, all quality fields kept raw.

    Aggregates are computed from this table (a new location/radius is a
    re-aggregation, never a re-download). Idempotency unit is the day-file:
    ingest replaces a whole (day, source_version) transactionally.
    """

    __tablename__ = "lightning_events"
    __table_args__ = (Index("ix_lightning_events_lat_lon", "lat", "lon"),)

    id: int | None = Field(default=None, primary_key=True)
    ts_utc: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    day: date = Field(index=True)
    lat: float
    lon: float
    peak_current_ka: float  # signed: negative = negative discharge
    multiplicity: int  # 0 means "stroke row", not missing
    number_of_sensors: int
    degrees_of_freedom: int | None = None
    ellipse_angle: float | None = None
    semi_major_axis: float | None = None
    semi_minor_axis: float | None = None
    chi_square_value: float | None = None
    rise_time: float | None = None
    peak_to_zero_time: float | None = None
    max_rate_of_rise: float | None = None
    cloud_indicator: int  # 0 = cloud-to-ground, 1 = cloud discharge
    angle_indicator: int | None = None
    signal_indicator: int | None = None
    timing_indicator: int | None = None
    source: str = Field(default="smhi-lightning", max_length=32)
    source_version: str = Field(default="1.0", max_length=16)


class LightningDailyRollup(SQLModel, table=True):
    """Sweden-wide daily lightning summaries for low-latency default charts."""

    __tablename__ = "lightning_daily_rollups"
    __table_args__ = (
        Index("ix_lightning_daily_rollups_day", "day"),
        UniqueConstraint(
            "source",
            "source_version",
            "day",
            name="uq_lightning_daily_rollup_source_day",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    day: date
    bucket_start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    bucket_end: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    cg_count: int
    all_count: int
    lightning_days: int
    max_abs_peak_ka: float | None = None
    strongest_event_time: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )
    source: str = Field(default="smhi-lightning", max_length=32)
    source_version: str = Field(default="1.0", max_length=16)


class Station(SQLModel, table=True):
    """SMHI metobs station measuring total cloud amount (parameter 16)."""

    __tablename__ = "stations"

    id: int = Field(primary_key=True)  # SMHI station id, not ours
    name: str = Field(max_length=128)
    lat: float
    lon: float
    active: bool
    source: str = Field(default="smhi-metobs", max_length=32)
    source_version: str = Field(default="1.0", max_length=16)


class CloudHourly(SQLModel, table=True):
    """Hourly total cloud cover at a metobs station (parameter 16, percent 0-100)."""

    __tablename__ = "cloud_hourly"
    __table_args__ = (
        Index("ix_cloud_hourly_station_ts", "station_id", "ts_utc"),
        UniqueConstraint(
            "station_id",
            "source",
            "source_version",
            "ts_utc",
            name="uq_cloud_hourly_station_ts",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    station_id: int = Field(foreign_key="stations.id", index=True)
    ts_utc: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    cloud_pct: float | None = None  # normalized 0-100; NULL = missing / not observable
    quality: str | None = Field(default=None, max_length=1)  # G or Y; kept, never filtered
    source: str = Field(default="smhi-metobs", max_length=32)
    source_version: str = Field(default="1.0", max_length=16)


class CloudRollup(SQLModel, table=True):
    """Station cloud summaries at serving resolutions, refreshed from cloud_hourly."""

    __tablename__ = "cloud_rollups"
    __table_args__ = (
        Index(
            "ix_cloud_rollups_station_resolution_start",
            "station_id",
            "resolution",
            "bucket_start",
        ),
        UniqueConstraint(
            "station_id",
            "source",
            "source_version",
            "resolution",
            "bucket_start",
            name="uq_cloud_rollup_station_resolution_start",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    station_id: int = Field(foreign_key="stations.id", index=True)
    resolution: str = Field(max_length=8, index=True)
    bucket_start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    bucket_end: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    observed_count: int
    expected_count: int
    missing_count: int
    mean_cloud_pct: float | None = None
    min_cloud_pct: float | None = None
    max_cloud_pct: float | None = None
    p05_cloud_pct: float | None = None
    p50_cloud_pct: float | None = None
    p95_cloud_pct: float | None = None
    source: str = Field(default="smhi-metobs", max_length=32)
    source_version: str = Field(default="1.0", max_length=16)
