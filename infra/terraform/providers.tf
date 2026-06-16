# providers.tf — credentials in, nothing else.
#
# Each provider takes exactly one secret, threaded from a variable (declared in
# variables.tf, supplied via terraform.tfvars — gitignored). We pass the tokens
# explicitly rather than relying on the providers' env-var fallbacks so the
# single source of truth is the tfvars file, not the operator's shell.

# Neon — manages the Postgres project/branch/role/database.
provider "neon" {
  api_key = var.neon_api_key
}

# Fly.io — manages the app shell, machines, and IPs for the backend container.
# (Image build + migrate happen via `flyctl deploy`; see the backend_fly module.)
provider "fly" {
  fly_api_token = var.fly_api_token
}

# Cloudflare — manages the Pages project (and optional custom domain) for the SPA.
# account_id is passed per-resource in the frontend_pages module; the token here
# must be scoped to that account (Pages + DNS edit).
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
