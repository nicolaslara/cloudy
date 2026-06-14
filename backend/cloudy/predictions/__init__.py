"""Predictions — the first model that has to beat the climatology baseline.

The method is *damped anomaly persistence*, the simplest forecaster that can
plausibly do better than the long-run normal without pretending to be physics:

    forecast(month at lead k) = climatology(month) + alpha(k) * recent_anomaly

A "normal" is the all-years mean for a calendar month; an "anomaly" is one
month's mean minus that normal. The recent anomaly is the last observed month's
departure from normal, and alpha(k) — the lag-k anomaly autocorrelation clamped
to [0, 1] — says how much of that departure is expected to carry forward k
months out. alpha decays toward zero with lead, and crucially alpha=0 reproduces
the climatology exactly: that invariant is what guarantees the model cannot lose
to the baseline on average. We never extrapolate a trend; we only let the most
recent surprise fade.

Everything is scored honestly against climatology on a rolling-origin,
expanding-window backtest (leave-future-out): fit alpha on training months only,
forecast the held-out future, and report skill = 1 - err_model/err_clim per lead.

Layering: predictions may lean on the foundation (core, db, ingest) and on
climatology (it *is* the baseline), but never on exploration. Nothing in the
foundation imports predictions.
"""
