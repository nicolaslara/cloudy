import logging

from fastapi import APIRouter
from sqlalchemy import text

from cloudy import __version__
from cloudy.db.session import get_engine

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    # /health must answer even when Postgres is down: degrade, never 500.
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        db = "up"
    except Exception:
        logger.exception("health: database ping failed")
        db = "down"
    return {
        "status": "ok" if db == "up" else "degraded",
        "db": db,
        "version": __version__,
    }
