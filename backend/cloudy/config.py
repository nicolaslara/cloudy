from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
    log_level: str = "INFO"
    raw_data_dir: str = "../data/raw"
    api_port: int = 8400
    api_docs: bool = True
    geocoder: str = "photon"
    cache_backend: str = "memory"


@lru_cache
def get_settings() -> Settings:
    return Settings()
