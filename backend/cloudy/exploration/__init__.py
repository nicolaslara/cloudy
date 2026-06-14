"""Exploration — the interactive data-lab read paths over raw history.

Where climatology answers "what is normal here", exploration answers "show me
exactly what happened", at whatever zoom the user is looking through. That makes
it the busy, detail-heavy half of the system: a level-of-detail planner that
picks a resolution and aggregation to fit the requested window into a point
budget, the raw cloud/lightning time-series readers it drives, and the
strokes/events readers that feed the map.

This complexity is deliberately fenced off here so the climatology deliverable
can be presented on its own. Layering: exploration depends only on the
foundation (core.{units,geo,cache,series_sql}, db, ingest); it is a sibling of
climatology and never imports it, nor it us.
"""
