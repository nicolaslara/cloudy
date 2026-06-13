"""Dispatch a validated LightningQuery to the series or strokes reader."""

from datetime import UTC, datetime

from sqlalchemy import Engine

from cloudy.core import lightning_events, lightning_series
from cloudy.core.lightning_query import LightningQuery
from cloudy.core.lightning_types import LightningResponse, LightningStrokesResponse
from cloudy.core.series_plan import plan_series


def execute(engine: Engine, query: LightningQuery) -> LightningResponse:
    spatial = query.spatial()
    date_to = query.resolved_date_to()
    generated_at = datetime.now(UTC).isoformat()
    spatial_meta = spatial.as_meta()

    if query.format == "series":
        # Counting matched events is a full scan of the window, so we only pay
        # for it when planning actually needs it. "auto" uses the count to decide
        # whether raw points fit, and a raw plan is capped against it, so those
        # paths must count before planning. A manual bucket aggregation, by
        # contrast, can be rejected as too large from the date range alone — so
        # we plan first there and let an unsafe request fail before we scan.
        # Either way we count at most once and reuse it as total_matched in meta.
        event_count = (
            lightning_series.count_events(engine, spatial, query.date_from, date_to)
            if query.aggregation in ("auto", "raw")
            else None
        )
        plan = plan_series(
            "lightning",
            query.date_from,
            date_to,
            query.aggregation,
            query.width_px,
            query.max_points,
            lightning_event_count=event_count,
        )
        if event_count is None:
            event_count = lightning_series.count_events(engine, spatial, query.date_from, date_to)
        series = lightning_series.query_series(engine, spatial, plan, query.date_from, date_to)
        return {
            "format": "series",
            "aggregation": query.aggregation,
            "resolved_resolution": plan.resolved_resolution,
            "spatial": spatial_meta,
            "series": series,
            "meta": {
                "from": query.date_from.isoformat(),
                "to": date_to.isoformat(),
                "sources": ["smhi-lightning"],
                "attribution": "Source: SMHI",
                "generated_at": generated_at,
                "total_matched": event_count,
                "returned": len(series),
                "requested_aggregation": plan.requested_aggregation,
                "resolved_resolution": plan.resolved_resolution,
                "mode": plan.mode,
                "representation": plan.representation,
                "target_points": plan.target_points,
                "point_count": len(series),
                "is_complete": True,
            },
        }

    events = lightning_events.query_events(
        engine,
        query.date_from,
        date_to,
        spatial,
        limit=query.limit,
    )
    strokes: LightningStrokesResponse = {
        "format": "strokes",
        "columns": events["columns"],
        "rows": events["rows"],
        "spatial": spatial_meta,
        "meta": {
            **events["meta"],
            "sources": ["smhi-lightning"],
            "attribution": "Source: SMHI",
            "generated_at": generated_at,
        },
    }
    return strokes
