from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default matches docker-compose.yml; production overrides via env.
    database_url: str = "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
    log_level: str = "INFO"
    api_port: int = 8400


@lru_cache
def get_settings() -> Settings:
    return Settings()
