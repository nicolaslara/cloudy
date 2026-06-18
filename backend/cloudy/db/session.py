from functools import lru_cache

from sqlalchemy import Engine, create_engine

from cloudy.config import get_settings

# libpq keepalive/timeout settings applied to every connection. These matter most
# against serverless Postgres (Neon), which will sever a live socket — compute
# autosuspend, a backend restart, a network blip — sometimes *while the client is
# blocked reading a query result*. Without keepalives that read blocks forever on
# a half-open TCP connection (the peer is gone but no FIN/RST arrived), and
# pool_pre_ping cannot help: it validates at checkout, not mid-statement. With
# keepalives the kernel probes the dead peer and the stuck read fails promptly
# with OperationalError, which is exactly what the ingest retry wrapper needs to
# reconnect. The kernel answers keepalive probes regardless of how long a real
# query runs, so a slow aggregation is never mistaken for a dead connection.
_CONNECT_ARGS = {
    "connect_timeout": 15,  # bound the initial connect (tolerates a Neon cold start)
    "keepalives": 1,
    "keepalives_idle": 30,  # start probing after 30s of silence
    "keepalives_interval": 10,
    "keepalives_count": 5,  # ~30 + 5*10 = ~80s to declare a dead peer
    # Linux-only: drop the connection if sent data goes unacked this long (ms).
    # Ignored on platforms without TCP_USER_TIMEOUT (e.g. macOS), where the
    # keepalive settings above do the job.
    "tcp_user_timeout": 60000,
}


# One process-wide engine (and its connection pool), memoized via lru_cache so
# every caller shares it. pool_pre_ping cheaply validates a connection before
# handing it out, so a pooled socket killed by an idle Postgres restart reconnects
# instead of surfacing as a stale-connection error to the request.
@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args=_CONNECT_ARGS,
    )
