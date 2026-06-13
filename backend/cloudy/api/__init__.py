from fastapi import FastAPI

from cloudy import __version__
from cloudy.api.cloud import router as cloud_router
from cloudy.api.geocode import router as geocode_router
from cloudy.api.health import router as health_router
from cloudy.api.lightning import router as lightning_router
from cloudy.api.station import router as station_router
from cloudy.config import get_settings
from cloudy.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    docs = "/docs" if settings.api_docs else None
    app = FastAPI(
        title="cloudy",
        version=__version__,
        docs_url=docs,
        redoc_url="/redoc" if settings.api_docs else None,
        openapi_url="/openapi.json" if settings.api_docs else None,
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(geocode_router, prefix="/api/v1")
    # GET /lightning?format=series|strokes — filter + presentation (see lightning_query.py)
    app.include_router(lightning_router, prefix="/api/v1")
    app.include_router(cloud_router, prefix="/api/v1")
    app.include_router(station_router, prefix="/api/v1")
    return app
