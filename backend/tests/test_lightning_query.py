"""LightningQuery spatial/presentation validation."""

import pytest
from pydantic import ValidationError

from cloudy.core.spatial import SpatialBounds
from cloudy.exploration.lightning_query import LightningQuery, spatial_meta


def test_default_is_sweden_series() -> None:
    query = LightningQuery()
    spatial = query.spatial()
    assert spatial.mode == "sweden"
    assert query.format == "series"
    assert query.aggregation == "auto"


def test_radius_derives_bbox_and_sets_mode() -> None:
    query = LightningQuery.model_validate(
        {"lat": 59.33, "lon": 18.06, "radius_km": 10},
    )
    spatial = query.spatial()
    assert spatial.mode == "radius"
    assert spatial.use_radius is True
    assert spatial.min_lon < 18.06 < spatial.max_lon


def test_bbox_and_radius_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        LightningQuery.model_validate(
            {
                "lat": 59.33,
                "lon": 18.06,
                "radius_km": 10,
                "bbox": "9,55,20,65",
            },
        )


def test_radius_requires_point() -> None:
    with pytest.raises(ValidationError):
        LightningQuery.model_validate({"radius_km": 10})


def test_bbox_parses_sweden_subset() -> None:
    query = LightningQuery.model_validate({"bbox": "11,55,19,60", "format": "strokes"})
    spatial = query.spatial()
    assert spatial.mode == "bbox"
    assert spatial.min_lon == 11


def test_spatial_bounds_meta() -> None:
    assert spatial_meta(SpatialBounds.from_radius(59.0, 18.0, 10))["mode"] == "radius"
    assert spatial_meta(SpatialBounds.sweden())["mode"] == "sweden"


def test_date_order_validated() -> None:
    with pytest.raises(ValidationError, match="from must be on or before to"):
        LightningQuery.model_validate({"from": "2018-07-31", "to": "2018-07-01"})
