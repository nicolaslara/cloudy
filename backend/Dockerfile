# Production image for the cloudy FastAPI backend.
#
# Two stages so the final image carries only the resolved virtualenv and the
# app — not uv, build caches, or the lockfile-resolution machinery. We pin uv
# and Python explicitly: the project targets 3.12 (pyproject requires-python
# >=3.12, ruff/mypy target py312), so we build and run on the same minor to
# avoid "works on my machine" drift between dev and Fly.

# --- builder: resolve and install dependencies into a project venv ----------
FROM ghcr.io/astral-sh/uv:0.6.7-python3.12-bookworm-slim AS builder

# Bytecode-compile on install (faster cold starts) and copy packages into the
# venv instead of symlinking from uv's cache, so the venv is self-contained and
# survives the stage boundary.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first, in their own layer, keyed only on the manifest +
# lockfile. App-code edits then reuse this layer instead of re-resolving deps.
# --no-install-project: the project itself is installed in the next step, after
# its source is copied. --no-dev: production venv carries no ruff/mypy/pytest.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Now the source, then install the project itself (the `cloudy` package and its
# `cloudy` console script) into the same venv.
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- runtime: slim image with just Python + the built venv + the app --------
FROM python:3.12-slim-bookworm AS runtime

# Don't write .pyc at runtime and keep stdout/stderr unbuffered so Fly's log
# stream shows uvicorn output immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as a non-root user — defence in depth, no reason for the API to be root.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Bring over the resolved venv and the application. alembic.ini and alembic/
# must ship too: `cloudy migrate` resolves the config relative to the package
# root (cloudy/db/migrate.py -> parents[2]/alembic.ini) and reads DATABASE_URL
# from settings, so the release_command can upgrade the DB on deploy.
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/cloudy /app/cloudy
COPY --from=builder --chown=appuser:appuser /app/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /app/alembic.ini /app/alembic.ini

USER appuser

# Fly sets PORT (we default it to 8080 in fly.toml). Bind 0.0.0.0 so the
# container is reachable from Fly's proxy. We reuse the project's own
# entrypoint (`cloudy serve`) rather than calling uvicorn directly, so host/
# port/log-level wiring stays in one place (cloudy/cli.py).
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "cloudy serve --host 0.0.0.0 --port ${PORT}"]
