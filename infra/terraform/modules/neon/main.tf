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
  name       = var.project_name
  region_id  = var.region_id
  pg_version = var.pg_version

  # Name the default branch's database and role so the connection string the app
  # receives points at `cloudy`/`cloudy`, matching local dev (docker-compose).
  branch {
    database_name = var.database_name
    role_name     = var.role_name
  }

  # Smallest autoscaling footprint + scale-to-zero compute: this is a low-traffic
  # API, and Neon bills by compute-hour. The endpoint suspends when idle and
  # resumes on the next connection (a brief cold start, acceptable here).
  default_endpoint_settings {
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 0.25
    suspend_timeout_seconds  = 0 # 0 = use Neon's default scale-to-zero timeout
  }
}
