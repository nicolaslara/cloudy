from fastapi import FastAPI

from cloudy import __version__
from cloudy.api.health import router as health_router
from cloudy.config import get_settings
from cloudy.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(title="cloudy", version=__version__)
    app.include_router(health_router, prefix="/api/v1")
    return app
