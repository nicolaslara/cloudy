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
  # The SPA's public origin, derived from the slug (mirrors frontend_pages's
  # pages_url output). Computed as a local rather than read back from the module
  # so backend_fly can lock CORS to it WITHOUT creating a backend<->pages cycle
  # (pages already depends on backend for VITE_API_URL).
  pages_url = var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "https://${local.pages_project}.pages.dev"
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

# 2) Backend — receives DATABASE_URL from Neon; exposes its public HTTPS URL.
module "backend_fly" {
  source = "./modules/backend_fly"

  app_name = local.fly_app_name
  org      = var.fly_org
  region   = var.fly_region

  # Terraform builds & pushes the image (via flyctl's remote builder), migrates,
  # and rolls the machine on every apply, so it needs the Fly token. image_label
  # is just the tag prefix; the module appends a content hash per release.
  fly_api_token = var.fly_api_token
  image_label   = var.backend_image_label

  database_url = module.neon.database_url

  # Lock the API's CORS to the SPA origin so no other site can call it.
  cors_allow_origins = local.pages_url

  min_machines_running = var.backend_min_machines_running
  memory_mb            = var.backend_memory_mb
  cpus                 = var.backend_cpus
}

# 3) Frontend — bakes the backend URL into the SPA build as VITE_API_URL.
module "frontend_pages" {
  source = "./modules/frontend_pages"

  account_id           = var.cloudflare_account_id
  cloudflare_api_token = var.cloudflare_api_token
  project_name         = local.pages_project
  production_branch    = var.pages_production_branch

  api_url = module.backend_fly.backend_url

  custom_domain = var.frontend_custom_domain
  # dns_zone_id left at its default (""); set it in tfvars to have Terraform
  # create the CNAME for a custom domain.
}
