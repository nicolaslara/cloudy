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
  # Neon requires TLS and exposes two hosts: a pgBouncer pooler and the direct
  # compute endpoint. The pooler is the safer default for the serverless backend
  # (it survives bursts of short-lived connections), so it backs `database_url`.
  # The direct host backs `database_url_direct` for one-off bulk work — see that
  # output's note.
  _host        = neon_project.this.database_host_pooler
  _host_direct = neon_project.this.database_host
  _qs          = "sslmode=require"

  _url_fmt = "postgresql+psycopg://%s:%s@%s/%s?%s"

  database_url = format(
    local._url_fmt,
    neon_project.this.database_user,
    neon_project.this.database_password,
    local._host,
    neon_project.this.database_name,
    local._qs,
  )

  database_url_direct = format(
    local._url_fmt,
    neon_project.this.database_user,
    neon_project.this.database_password,
    local._host_direct,
    neon_project.this.database_name,
    local._qs,
  )
}

output "database_url" {
  description = "SQLAlchemy/psycopg connection string for the app's DATABASE_URL (postgresql+psycopg://...). Pooled host. Sensitive: contains the role password."
  value       = local.database_url
  sensitive   = true
}

output "database_url_direct" {
  description = <<-EOT
    Same credentials as database_url but pointed at Neon's DIRECT compute host
    (no pgBouncer). Use this for the one-off historical backfill and other long,
    transaction-heavy jobs: the pooler caps a transaction's lifetime and can
    sever mid-COPY on multi-million-row loads, whereas the direct endpoint holds
    a single long connection. The running app keeps using the pooled URL.
    Sensitive: contains the role password.
  EOT
  value       = local.database_url_direct
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
