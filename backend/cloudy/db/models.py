from datetime import datetime

from sqlalchemy import Column, DateTime
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
