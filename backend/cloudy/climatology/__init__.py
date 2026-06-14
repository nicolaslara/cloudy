"""Climatology — long-run historical "normals" for cloud and lightning.

This is the permanent baseline: the average behaviour of a place, computed from
all the history we hold, that every later model (statistical or AI) must beat
before it ships. The UI labels it "Normals"; the domain term is "climatology".

A normal answers "what is typical here for this month / day-of-year / year",
and — for the month in progress — blends what has been observed so far with the
climatological tail for the days still to come, so the product can show a live,
honest expectation without any forecasting model.

Layering: this package depends only on the foundation (core, db, ingest); it is
a sibling of exploration and never imports it.
"""
