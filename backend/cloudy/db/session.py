from functools import lru_cache

from sqlalchemy import Engine, create_engine

from cloudy.config import get_settings


# One process-wide engine (and its connection pool), memoized via lru_cache so
# every caller shares it. pool_pre_ping cheaply validates a connection before
# handing it out, so a pooled socket killed by an idle Postgres restart reconnects
# instead of surfacing as a stale-connection error to the request.
@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)
