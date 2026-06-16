# Outputs — the database URL in the EXACT shape the app expects.
#
# backend/cloudy/config.py declares:
#   database_url: str = "postgresql+psycopg://cloudy:cloudy@localhost:5432/cloudy"
# pydantic-settings reads it from the env var DATABASE_URL. The app uses psycopg
# (v3), so the SQLAlchemy URL scheme MUST be `postgresql+psycopg://` — Neon's
# native `connection_uri` is bare `postgresql://`, which SQLAlchemy would resolve
# to the wrong (psycopg2) driver. So we rebuild the URL from the project's parts
# and inject the `+psycopg` driver, preserving query params (sslmode, etc.).

locals {
  # Neon requires TLS; the pooler host is the safer default for a serverless
  # backend. Swap `database_host_pooler` -> `database_host` to use a direct
  # connection instead.
  _host = neon_project.this.database_host_pooler
  _qs   = "sslmode=require"

  database_url = format(
    "postgresql+psycopg://%s:%s@%s/%s?%s",
    neon_project.this.database_user,
    neon_project.this.database_password,
    local._host,
    neon_project.this.database_name,
    local._qs,
  )
}

output "database_url" {
  description = "SQLAlchemy/psycopg connection string for the app's DATABASE_URL (postgresql+psycopg://...). Sensitive: contains the role password."
  value       = local.database_url
  sensitive   = true
}

output "project_id" {
  description = "Neon project ID (for console links / debugging)."
  value       = neon_project.this.id
}

output "database_host" {
  description = "Pooled database host (non-secret)."
  value       = local._host
}
