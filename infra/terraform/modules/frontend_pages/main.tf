# modules/frontend_pages — the Cloudflare Pages project for the React SPA.
#
# Build config and the prod env var come straight from the frontend:
#   - build command:    `pnpm build`  (package.json -> tsc --noEmit && vite build)
#   - output directory: `dist`        (Vite default; vite.config.ts sets no outDir)
#   - root directory:   `frontend`    (the SPA lives there)
#
# VITE_API_URL is the one knob that wires the SPA to the backend. Vite inlines
# `import.meta.env.VITE_*` at BUILD time, so this must be present when Pages runs
# the build — hence it's a build-time env var on the production deployment config,
# not a runtime binding. In dev the SPA keeps the Vite proxy (vite.config.ts);
# in prod the API client prefixes requests with VITE_API_URL (a frontend-agent
# change). Setting it here as `plain_text` (it's a public URL, not a secret).
#
# Connecting the git repo: a `source` block (GitHub/GitLab) would let Pages build
# on push, but that requires a pre-linked VCS account on the Cloudflare side
# (can't be done in Terraform) and would couple this to a specific git host. We
# deliberately leave `source` out: the SPA is built and uploaded by CI
# (`.github/workflows/deploy.yml` runs `pnpm build` + `wrangler pages deploy`), so
# this module owns only the Pages *project* — its settings and the build-time
# VITE_API_URL. The build_config below is only used if a git-connected build is
# ever turned on; wrangler direct-upload from CI ignores it. Add a `source` block
# later if git-connected builds are wanted.

resource "cloudflare_pages_project" "this" {
  account_id        = var.account_id
  name              = var.project_name
  production_branch = var.production_branch

  # v5 expresses these as attribute maps (`= {}`), not nested blocks.
  build_config = {
    build_command   = var.build_command
    destination_dir = var.destination_dir
    root_dir        = var.root_dir
  }

  deployment_configs = {
    # Production carries the real backend URL. Preview deployments get the same
    # value so PR previews talk to the same API (fine for a single backend; give
    # preview its own VITE_API_URL here if a staging backend is added later).
    production = {
      compatibility_date = var.compatibility_date
      env_vars = {
        VITE_API_URL = {
          type  = "plain_text"
          value = var.api_url
        }
      }
    }
    preview = {
      compatibility_date = var.compatibility_date
      env_vars = {
        VITE_API_URL = {
          type  = "plain_text"
          value = var.api_url
        }
      }
    }
  }
}

# --- Optional custom domain ------------------------------------------------
#
# Attaching a domain to the Pages project (count-gated on custom_domain being
# set). Per Cloudflare, this does NOT create the DNS record — that's the
# cloudflare_dns_record below, which we only create when a zone id is also given.

resource "cloudflare_pages_domain" "this" {
  count        = var.custom_domain == "" ? 0 : 1
  account_id   = var.account_id
  project_name = cloudflare_pages_project.this.name
  name         = var.custom_domain
}

# The CNAME pointing the custom domain at the Pages project. Only created when
# the caller supplies a zone id (otherwise they manage DNS themselves).
resource "cloudflare_dns_record" "pages_cname" {
  count   = var.custom_domain != "" && var.dns_zone_id != "" ? 1 : 0
  zone_id = var.dns_zone_id
  name    = var.custom_domain
  type    = "CNAME"
  content = "${cloudflare_pages_project.this.name}.pages.dev"
  proxied = true
  ttl     = 1 # 1 = automatic (required by the cloudflare v5 provider)
}
