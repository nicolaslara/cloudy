# variables.tf — every knob the stack needs, with safe defaults where one exists.
#
# Secrets are marked `sensitive` and have NO default: Terraform will refuse to
# plan without them, which is what we want — there is no "accidentally ran with a
# blank token" path. Supply them in terraform.tfvars (gitignored) or via
# TF_VAR_* env vars in CI.

# ---------------------------------------------------------------------------
# Secrets (no defaults — must be provided; never commit real values)
# ---------------------------------------------------------------------------

variable "neon_api_key" {
  description = "Neon API key (https://console.neon.tech -> Account -> API keys)."
  type        = string
  sensitive   = true
}

variable "fly_api_token" {
  description = "Fly.io API token (`flyctl auth token`). Org-scoped is fine."
  type        = string
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token scoped to the target account: Pages (edit) and, if a custom domain is used, DNS (edit)."
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID that owns the Pages project."
  type        = string
  # Not a secret, but account-specific — no sensible default.
}

# ---------------------------------------------------------------------------
# Non-secret knobs (sensible defaults; override in tfvars as needed)
# ---------------------------------------------------------------------------

variable "project_slug" {
  description = "Base name for all resources. The deploy contract fixes the derived names: Fly app <slug>-api, Pages project <slug>-web."
  type        = string
  default     = "cloudy"
}

variable "neon_region_id" {
  description = "Neon deployment region. Use `aws-eu-central-1` (Frankfurt) to sit near Sweden's SMHI data and the Fly EU region."
  type        = string
  default     = "aws-eu-central-1"
}

variable "neon_pg_version" {
  description = "Postgres major version for the Neon project."
  type        = number
  default     = 16
}

variable "fly_region" {
  description = "Primary Fly.io region for the backend machine. `arn` (Stockholm) keeps the API next to its Swedish data and the Neon EU region."
  type        = string
  default     = "arn"
}

variable "fly_org" {
  description = "Fly.io organization slug to create the app in."
  type        = string
  default     = "personal"
}

variable "backend_image" {
  description = <<-EOT
    Fully-qualified backend container image the Fly machine runs, e.g.
    `registry.fly.io/cloudy-api:deployment-XXXX`. This is BUILT AND PUSHED BY
    `flyctl deploy` (which reads backend/Dockerfile), not by Terraform — the
    andrewbaxter/fly provider runs a pre-built image, it does not build one.
    Leave at the default for the first `terraform apply` (a placeholder image so
    the machine resource is well-formed); then run `flyctl deploy` to build,
    push, run `cloudy migrate` as the release_command, and roll the real image.
    See the backend_fly module and infra/terraform/README.md.
  EOT
  type        = string
  default     = "registry.fly.io/cloudy-api:latest"
}

variable "backend_min_machines_running" {
  description = "Min machines kept running. 0 = scale-to-zero (cheapest; first request after idle pays a cold start). Set to 1 to avoid cold starts."
  type        = number
  default     = 0
}

variable "backend_memory_mb" {
  description = "RAM (MB) for the backend machine. 512 is comfortable for FastAPI + psycopg; bump if model/backtest work runs in-process."
  type        = number
  default     = 512
}

variable "backend_cpus" {
  description = "vCPU count for the backend machine."
  type        = number
  default     = 1
}

# ---------------------------------------------------------------------------
# Frontend / Pages
# ---------------------------------------------------------------------------

variable "pages_production_branch" {
  description = "Git branch Cloudflare Pages treats as production."
  type        = string
  default     = "main"
}

variable "frontend_custom_domain" {
  description = "Optional custom domain for the SPA (e.g. `cloudy.example.com`). Empty string disables custom-domain wiring; the *.pages.dev URL is always available."
  type        = string
  default     = ""
}
