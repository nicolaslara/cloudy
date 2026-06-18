# main.tf — composes the three modules into one stack and wires the edges:
#
#   neon ──(database_url)──> backend_fly ──(backend_url)──> frontend_pages
#
# The whole point of one root: the Neon connection string flows into the Fly
# machine's env, and the Fly app's public URL flows into the SPA's build-time
# VITE_API_URL. No value is typed twice; change a region or a name in one place.
#
# Names are derived from project_slug to honor the deploy contract:
#   Fly app       = "${slug}-api"  -> cloudy-api
#   Pages project = "${slug}-web"  -> cloudy-web

locals {
  fly_app_name      = "${var.project_slug}-api"
  pages_project     = "${var.project_slug}-web"
  raw_bucket_name   = var.raw_archive_bucket_name != "" ? var.raw_archive_bucket_name : "${var.project_slug}-raw"
  neon_project_name = var.project_slug
}

# Raw SMHI archive storage. This is not served by the app; it is an operator
# cache for initial production loads and scheduled ingest jobs so they can replay
# archived CSVs instead of re-downloading the whole history.
resource "cloudflare_r2_bucket" "raw_archive" {
  account_id    = var.cloudflare_account_id
  name          = local.raw_bucket_name
  jurisdiction  = var.raw_archive_bucket_jurisdiction
  location      = var.raw_archive_bucket_location
  storage_class = "Standard"
}

# 1) Database first — everything downstream needs its connection string.
module "neon" {
  source = "./modules/neon"

  project_name              = local.neon_project_name
  region_id                 = var.neon_region_id
  pg_version                = var.neon_pg_version
  org_id                    = var.neon_org_id
  history_retention_seconds = var.neon_history_retention_seconds
  autoscaling_max_cu        = var.neon_autoscaling_max_cu
  # database_name / role_name default to "cloudy" (matches local dev).
}

# 2) Backend — the Fly app + public IPs only. The image build, `cloudy migrate`,
# and the machine roll are owned by CI (`flyctl deploy`); the machine's shape lives
# in backend/fly.toml and runtime config (DATABASE_URL from Neon, CORS_ALLOW_ORIGINS)
# is set as Fly app secrets out of band. See modules/backend_fly for the rationale.
module "backend_fly" {
  source = "./modules/backend_fly"

  app_name = local.fly_app_name
  org      = var.fly_org
}

# 3) Frontend — the Pages project only. The SPA is built and uploaded by CI
# (`wrangler pages deploy`, with VITE_API_URL baked in from the deploy workflow's
# own secret). api_url is still wired into the project's build-time env so a
# git-connected Pages build would get the right backend URL if that's ever enabled.
module "frontend_pages" {
  source = "./modules/frontend_pages"

  account_id        = var.cloudflare_account_id
  project_name      = local.pages_project
  production_branch = var.pages_production_branch

  api_url = module.backend_fly.backend_url

  custom_domain = var.frontend_custom_domain
  # dns_zone_id left at its default (""); set it in tfvars to have Terraform
  # create the CNAME for a custom domain.
}
