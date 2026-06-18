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

variable "neon_org_id" {
  description = "Neon organization id that owns the project. Required for org-scoped API keys (Neon's current default); leave empty for a legacy personal account. Find it via the Neon console -> Organization settings, or GET /api/v2/users/me/organizations."
  type        = string
  default     = ""
}

variable "neon_history_retention_seconds" {
  description = "Point-in-time-restore window for the Neon branch. Free plans cap this at 21600s (6h) AND count retained history against the 512 MB storage limit, so on the free tier a shorter window leaves more room for live data; 0 disables PITR. Raise it on a paid plan for a real restore window."
  type        = number
  default     = 21600
}

variable "neon_autoscaling_max_cu" {
  description = "Maximum Neon compute size (CUs) the endpoint may autoscale to under load. Min is fixed at 0.25 CU with scale-to-zero when idle, so this only adds cost while compute is busy. Default 0.25 = flat smallest footprint; raise it (e.g. 4) to let a historical backfill burst, after which compute settles back down on its own."
  type        = number
  default     = 0.25
}

variable "fly_org" {
  description = "Fly.io organization slug to create the app in."
  type        = string
  default     = "personal"
}

# Fly region, machine size, and scale-to-zero now live in backend/fly.toml (the
# machine is deployed by CI's `flyctl deploy`, not Terraform), so they are no
# longer Terraform variables.

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

# ---------------------------------------------------------------------------
# Raw data archive
# ---------------------------------------------------------------------------

variable "raw_archive_bucket_name" {
  description = "Cloudflare R2 bucket for the SMHI raw archive. Empty = <project_slug>-raw."
  type        = string
  default     = ""
}

variable "raw_archive_bucket_location" {
  description = "Best-effort R2 bucket location for the raw archive. `weur` keeps it in Western Europe."
  type        = string
  default     = "weur"
}

variable "raw_archive_bucket_jurisdiction" {
  description = "R2 jurisdiction guarantee for the raw archive bucket."
  type        = string
  default     = "eu"
}
