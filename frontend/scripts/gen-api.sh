#!/usr/bin/env bash
#
# Regenerate the OpenAPI schema dump and the TypeScript types derived from it.
#
# The story: api/cloud.ts and api/lightning.ts used to hand-mirror the backend's
# response shapes, which drifted silently whenever the Python types changed.
# This script closes that loop — it asks the FastAPI app itself for its schema
# and turns it into TypeScript, so the frontend types are a mechanical
# projection of the backend contract rather than a hopeful copy.
#
# We dump the schema offline (no running server needed) by importing the app
# factory and calling .openapi() directly. That keeps `pnpm gen:api` usable in
# CI and on a laptop without spinning up uvicorn or a database.
set -euo pipefail

# Resolve paths relative to this script so the command works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="$(cd "${FRONTEND_DIR}/../backend" && pwd)"

SCHEMA_JSON="${FRONTEND_DIR}/src/api/openapi.json"
SCHEMA_TS="${FRONTEND_DIR}/src/api/schema.gen.ts"

echo "gen:api → dumping OpenAPI schema from cloudy.api.create_app()"
# create_app lives in backend/cloudy/api/__init__.py; calling .openapi() builds
# the full schema dict without binding a port. We run it from the backend dir so
# uv picks up that project's environment.
( cd "${BACKEND_DIR}" && uv run python -c \
  "import json, cloudy.api as a; print(json.dumps(a.create_app().openapi(), indent=2))" \
) > "${SCHEMA_JSON}"

# Fail loudly if the dump is not valid JSON — a silent empty/garbage file would
# otherwise produce a confusing openapi-typescript error downstream.
node -e "JSON.parse(require('fs').readFileSync(process.argv[1],'utf8'))" "${SCHEMA_JSON}"

echo "gen:api → emitting ${SCHEMA_TS}"
pnpm exec openapi-typescript "${SCHEMA_JSON}" -o "${SCHEMA_TS}"

echo "gen:api → done"
