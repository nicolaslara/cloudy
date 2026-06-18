# modules/neon — one Neon project, with its default branch's database and role
# named to match the app.
#
# Why one resource does it all: `neon_project` provisions the project, a default
# branch, a primary read-write endpoint, a role, and a database in a single
# create. We name the default database/role via the `branch` block instead of
# adding separate `neon_database`/`neon_role` resources — fewer moving parts, and
# the project's own outputs (`connection_uri`, `database_*`) already describe the
# exact credentials, so there is nothing to reconcile.
#
# Pooled vs direct connection: the project exposes both a direct host and a
# pgBouncer pooler host. A scale-to-zero FastAPI machine opens few connections,
# so either works; we surface both and let the root choose (default: pooled,
# which is the safer default for a serverless backend that may scale out later).

resource "neon_project" "this" {
  name                      = var.project_name
  region_id                 = var.region_id
  pg_version                = var.pg_version
  history_retention_seconds = var.history_retention_seconds

  # Neon scopes projects to an organization for org-bound API keys (the current
  # default). Pass null when empty so legacy personal accounts, which reject the
  # field, still work — the conditional keeps one module valid for both.
  org_id = var.org_id != "" ? var.org_id : null

  # Name the default branch's database and role so the connection string the app
  # receives points at `cloudy`/`cloudy`, matching local dev (docker-compose).
  branch {
    database_name = var.database_name
    role_name     = var.role_name
  }

  # Smallest autoscaling footprint + scale-to-zero compute: this is a low-traffic
  # API, and Neon bills by compute-hour. The endpoint suspends when idle and
  # resumes on the next connection (a brief cold start, acceptable here).
  #
  # `autoscaling_max_cu` is a knob, not a fixed size: min stays at 0.25 CU so the
  # endpoint still scales to zero when idle (no standing cost), while a higher max
  # lets the compute burst for heavy work — notably a one-time historical backfill,
  # whose bulk inserts and percentile rollups are CPU-bound. Leaving max above the
  # min costs nothing at rest; you only pay the larger size for the minutes it is
  # actually under load.
  default_endpoint_settings {
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = var.autoscaling_max_cu
    suspend_timeout_seconds  = 0 # 0 = use Neon's default scale-to-zero timeout
  }
}
