from fastapi import FastAPI

from cloudy import __version__
from cloudy.api.geocode import router as geocode_router
from cloudy.api.health import router as health_router
from cloudy.api.station import router as station_router
from cloudy.climatology.api import router as climatology_router
from cloudy.config import get_settings
from cloudy.exploration.api_cloud import router as exploration_cloud_router
from cloudy.exploration.api_lightning import router as exploration_lightning_router
from cloudy.logging import configure_logging


# App factory (uvicorn runs it with factory=True): settings are read once here,
# so logging and the /docs toggle are wired before any request is served.
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
    # Foundation surface: health, geocoding, station lookup.
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(geocode_router, prefix="/api/v1")
    app.include_router(station_router, prefix="/api/v1")

    # Exploration — the interactive data-lab read paths, namespaced under
    # /exploration so the climatology deliverable can be presented on its own.
    # The lightning route serves both series and strokes via ?format=.
    app.include_router(exploration_lightning_router, prefix="/api/v1")
    app.include_router(exploration_cloud_router, prefix="/api/v1")

    # Climatology — the "Normals" deliverable. Its routes already carry the
    # /climatology prefix, so it mounts under the same /api/v1 base.
    app.include_router(climatology_router, prefix="/api/v1")
    return app
