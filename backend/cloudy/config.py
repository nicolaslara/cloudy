from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Defaults match docker-compose.yml and a cwd of backend/ (how all entry
    # points run); production overrides via env.
    database_url: str = "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
    log_level: str = "INFO"
    raw_data_dir: str = "../data/raw"
    api_port: int = 8400  # frontend/vite.config.ts proxy target must match
    api_docs: bool = True  # /docs, /redoc, /openapi.json; set false to 404 them
    geocoder: str = "photon"  # or "nominatim" (on-submit only; its policy bans autocomplete)
    cache_backend: str = "memory"  # process-local; switch to a shared backend when >1 server


@lru_cache
def get_settings() -> Settings:
    return Settings()
