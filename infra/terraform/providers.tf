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

# Fly.io — manages the app shell and public IPs for the backend. The image build,
# `cloudy migrate`, and the machine roll are owned by CI (`flyctl deploy`); this
# provider just needs a token to manage the app + IPs. See the backend_fly module.
provider "fly" {
  fly_api_token = var.fly_api_token
}

# Cloudflare — manages the Pages project, the R2 raw archive bucket, and
# optional custom-domain DNS for the SPA.
# account_id is passed per-resource in the frontend_pages module; the token here
# must be scoped to that account (Pages + R2, plus DNS edit for custom domains).
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
