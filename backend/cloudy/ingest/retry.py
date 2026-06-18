"""Reconnect-and-retry wrapper for long backfills against serverless Postgres.

A multi-million-row backfill holds the database busy for many minutes, and
serverless Postgres (Neon) will occasionally sever a live connection in that
window — compute autoscaling/suspend, a backend restart, or a brief network
blip all surface as ``OperationalError: server closed the connection
unexpectedly`` *mid-statement*. ``pool_pre_ping`` cannot help here: it validates
a connection at checkout, not while a statement is in flight.

Every ingest unit (one lightning day, one cloud station) is written in its own
idempotent transaction (delete-then-insert / upsert), so the safe response to a
dropped connection is simply to discard the dead pool and re-run the unit. We
retry only connection-level errors; a data or constraint error is a real bug and
must fail fast rather than loop.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from sqlalchemy import Engine
from sqlalchemy.exc import InterfaceError, OperationalError

logger = logging.getLogger(__name__)

# psycopg raises OperationalError when the server closes the socket and
# InterfaceError when the cursor/connection is already gone; both mean "the
# connection died" and are safe to retry for an idempotent unit. Notably absent:
# IntegrityError/DataError/ProgrammingError — those are bugs, not blips.
_TRANSIENT_DB_ERRORS = (OperationalError, InterfaceError)


def with_reconnect[T](
    engine: Engine,
    unit: Callable[[], T],
    *,
    what: str,
    attempts: int = 6,
    base_delay: float = 2.0,
) -> T:
    """Run one idempotent ingest unit, reconnecting if the connection drops.

    ``unit`` must be self-contained: it opens its own transaction(s) via
    ``engine.begin()`` and can be re-run from scratch. On a transient connection
    error we dispose the pool (so the dead socket is gone) and call ``unit``
    again; the next ``engine.begin()`` then checks out a fresh, pre-pinged
    connection. Backoff is linear and bounded by ``attempts`` so a genuinely
    unreachable database still fails in finite time with the original error.
    """
    for attempt in range(1, attempts + 1):
        try:
            return unit()
        except _TRANSIENT_DB_ERRORS as exc:
            if attempt == attempts:
                raise
            wait = base_delay * attempt
            logger.warning(
                "%s: database connection lost (%s) — reconnect %d/%d in %.0fs",
                what,
                exc.__class__.__name__,
                attempt,
                attempts,
                wait,
            )
            # Drop the whole pool: the broken connection (and any siblings the
            # same server event killed) must not be handed back out.
            engine.dispose()
            time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover
