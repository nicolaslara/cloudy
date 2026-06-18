# versions.tf — the provider contract for the whole stack.
#
# Why pin here (and only here): Terraform resolves provider versions once, at the
# root. Modules declare which providers they *use* (in each module's versions.tf)
# but must not pin versions — that's this file's job, so the three pieces of the
# stack can never drift onto mismatched provider builds.
#
# Provider choices (the deploy contract asked us to pick the most-maintained of
# each; the reasoning is recorded so a future reader doesn't re-litigate it):
#
#   neon  -> kislerdm/neon
#     The de-facto community provider and the one Neon's own docs point at
#     (https://neon.com/docs/reference/terraform). Actively released
#     (0.13.0, Jan 2026). The official-org alternative is far less complete.
#
#   fly   -> andrewbaxter/fly
#     Fly.io abandoned their own provider (fly-apps/fly) and now actively
#     discourages Terraform for Fly. andrewbaxter/fly is the maintained
#     community fork. NOTE (see backend_fly module + README): this provider
#     models an *app + machines + IPs*, NOT a Dockerfile build or a
#     release_command. So the backend_fly module shells out to flyctl's remote
#     builder (terraform_data.image_push) to build & push the image during apply,
#     then Terraform rolls the machine onto it and runs `cloudy migrate` itself
#     (terraform_data.migrate) — there is no flyctl deploy / CI roll. Terraform
#     owns the app shell, the DATABASE_URL secret, the IPs, and the deploy. Both
#     `flyctl` and `uv` must be installed where `terraform apply` runs.
#
#   cloudflare -> cloudflare/cloudflare (v5)
#     The official provider. v5 is the current line (5.20.x as of Jun 2026) and
#     is where cloudflare_pages_project receives ongoing fixes. We pin to the v5
#     major and let patch/minor float.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.13" # 0.13.x; pre-1.0, so we hold the minor and float patch.
    }

    fly = {
      source  = "andrewbaxter/fly"
      version = "~> 0.1" # community fork; pre-1.0, minor-pinned.
    }

    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0" # v5 major line; floats minor/patch within v5.
    }
  }
}
