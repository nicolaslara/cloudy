"""Lightning response limits shared by query validation and readers.

These live in their own tiny module to break an import cycle: both the query
validator and series_plan need the caps, and neither should depend on the other.
The chart cap bounds a forced-raw bar series; the map caps bound how many
individual strokes we'll hand the map before it has to sample.
"""

MAX_RAW_LIGHTNING_CHART_EVENTS = 20_000
DEFAULT_MAP_STROKE_POINTS = 25_000
MAX_MAP_STROKE_POINTS = 50_000
