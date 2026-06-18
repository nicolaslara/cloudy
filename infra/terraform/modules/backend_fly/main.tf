# modules/backend_fly — the Fly *app shell* and public IPs for the backend.
#
# Scope: this module provisions only what is declarative and stable — the Fly app
# and its IPv4/IPv6 addresses. It deliberately does NOT build the image, run
# migrations, or roll a machine. Those are owned by CI: `.github/workflows/
# deploy.yml` runs `flyctl deploy`, which builds backend/Dockerfile, runs `cloudy
# migrate` as the fly.toml [deploy] release_command, and rolls the machine. The
# machine's shape (region, size, scale-to-zero) lives in backend/fly.toml, and
# runtime config (DATABASE_URL, CORS_ALLOW_ORIGINS) lives in Fly *app secrets*
# (`fly secrets set`), so it is injected into every machine and survives each roll.
#
# Why split it this way: the andrewbaxter/fly provider models app + machines + IPs
# but can't build a Dockerfile or run a release hook, and a Terraform-owned machine
# fights CI over the machine's image and env on every deploy (a `flyctl deploy`
# roll would drop Terraform-set machine env). Letting flyctl own the machine keeps
# a single deploy path (push to main) and one home for runtime config (Fly
# secrets). The app and IPs change rarely, so Terraform keeps them.
#
# Bootstrap order for a fresh environment: `terraform apply` first (creates the app
# + IPs here, plus Neon, Pages, and R2), then `fly secrets set` the runtime config,
# then a CI deploy (or a manual `flyctl deploy`) creates the first machine + image.

# The application object on Fly. `name` is globally unique within Fly's registry
# of app names; the contract reserves `cloudy-api`.
resource "fly_app" "this" {
  name = var.app_name
  org  = var.org
}

# Public addresses. Fly needs at least one dedicated IPv6 (free) plus a shared
# IPv4 for HTTPS to reach the app. We allocate both explicitly so `apply` is
# deterministic rather than relying on implicit shared-IP assignment.
resource "fly_ip" "v6" {
  app  = fly_app.this.name
  type = "v6"
}

resource "fly_ip" "v4" {
  app  = fly_app.this.name
  type = "v4"
}
