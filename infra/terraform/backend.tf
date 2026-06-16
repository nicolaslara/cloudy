# backend.tf — Terraform STATE backend (not the app backend).
#
# State is LOCAL for now, on purpose: this is a one-operator hobby stack, and a
# local terraform.tfstate is the simplest thing that works. State contains
# secrets (the Neon password, tokens), so it MUST stay out of git — the repo's
# root .gitignore already ignores `*.tfstate`, `*.tfstate.*`, and `.terraform/`
# (owned by the runbook agent). Do not commit terraform.tfstate.
#
# We declare an explicit local backend rather than relying on the implicit
# default so this decision is visible and easy to flip.
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}

# WHEN TO MOVE TO REMOTE STATE:
# As soon as a second person (or CI) runs apply, switch to a remote backend so
# state is shared and locked. Lowest-friction options, in order:
#
#   1. Terraform Cloud / HCP (free tier, built-in locking):
#        terraform { cloud { organization = "<org>"; workspaces { name = "cloudy" } } }
#
#   2. Neon itself can't host state; use any S3-compatible bucket (Cloudflare R2
#      works and you already have a Cloudflare account):
#        terraform {
#          backend "s3" {
#            bucket                      = "cloudy-tfstate"
#            key                         = "infra/terraform.tfstate"
#            region                      = "auto"
#            endpoints                   = { s3 = "https://<accountid>.r2.cloudflarestorage.com" }
#            skip_credentials_validation = true
#            skip_region_validation      = true
#            skip_requesting_account_id  = true
#            use_path_style              = true
#          }
#        }
#
# Either way, migrate with `terraform init -migrate-state` after editing this file.
