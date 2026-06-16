# modules/backend_fly — the Fly app shell for the FastAPI backend.
#
# READ THIS FIRST — the build/migrate split (the one non-obvious thing here):
#
# The andrewbaxter/fly provider models an *app + machines + IPs*. It does NOT
# build a Dockerfile and it has NO release_command hook. Fly's own deploy flow
# (`flyctl deploy`, reading backend/fly.toml) is what builds backend/Dockerfile,
# pushes the image to registry.fly.io, and runs the release_command
# (`cloudy migrate` -> alembic upgrade head) before the new machine takes
# traffic. That is the boring, supported path and the simplest thing that works.
#
# So responsibilities divide cleanly:
#   Terraform (this module): create the app, allocate IPv4/IPv6, run a machine,
#                            and — critically — inject DATABASE_URL.
#   flyctl deploy:           build the image, run migrations, roll the machine.
#
# The DATABASE_URL is delivered as a machine env value sourced from the Neon
# module output. It carries the role password, so var.database_url is sensitive
# and the value never appears in code — only in (gitignored) state and tfvars.
# (`flyctl secrets set` would be the alternative, but then the value would live
# outside Terraform; keeping it on the Terraform-managed machine env keeps Neon
# -> Fly a single declarative edge.)

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

# The machine that runs the container. One machine in one region is plenty for a
# low-traffic API; add more `fly_machine` blocks (or count) to scale out.
#
# Port binding: the app's entrypoint is `cloudy serve --host 0.0.0.0 --port
# $PORT` (see backend/cloudy/cli.py; PORT is set by Fly to var.internal_port).
# We expose it on 443 (TLS) and 80 (redirected to HTTPS) via the services block.
resource "fly_machine" "api" {
  app    = fly_app.this.name
  region = var.region
  name   = "${var.app_name}-machine"
  image  = var.image

  cpus     = var.cpus
  cpu_type = var.cpu_type
  memory   = var.memory_mb

  # Everything the container needs at runtime. PORT tells the app which port to
  # bind; DATABASE_URL is the Neon connection string (sensitive). env values
  # must be strings, hence tostring() on the port.
  env = {
    PORT               = tostring(var.internal_port)
    DATABASE_URL       = var.database_url
    CORS_ALLOW_ORIGINS = var.cors_allow_origins
  }

  # Expose the HTTP service. Fly's edge terminates TLS on 443 and forwards plain
  # HTTP to internal_port; port 80 force-redirects to HTTPS.
  services = [
    {
      protocol      = "tcp"
      internal_port = var.internal_port
      ports = [
        {
          port     = 443
          handlers = ["tls", "http"]
        },
        {
          port        = 80
          handlers    = ["http"]
          force_https = true
        },
      ]
    },
  ]

  # The image is rolled by `flyctl deploy`, which mutates the machine out of
  # band. Ignore image drift so a routine `terraform apply` doesn't fight the
  # deploy pipeline by reverting to var.image.
  lifecycle {
    ignore_changes = [image]
  }
}

# NOTE on min_machines_running / scale-to-zero: autostop/autostart is a property
# of Fly's *proxy services* config (set in fly.toml: `min_machines_running`,
# `auto_stop_machines`). The andrewbaxter provider doesn't expose it on
# fly_machine, so var.min_machines_running is surfaced for documentation and is
# applied via backend/fly.toml at deploy time. It's wired through here so the
# value has one home (root variables) even though flyctl consumes it.
