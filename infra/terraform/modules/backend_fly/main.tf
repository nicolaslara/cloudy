# modules/backend_fly — the Fly app + machine for the FastAPI backend, and the
# Terraform-owned deploy of its image.
#
# READ THIS FIRST — Terraform is the single deploy path here (no flyctl deploy /
# CI roll). The andrewbaxter/fly provider models an *app + machines + IPs*; it
# can't build a Dockerfile and has no release_command hook. So the module borrows
# flyctl's REMOTE builder for the one thing the provider can't do — build & push
# the image — and Terraform does everything else itself: roll the machine onto the
# new image and run migrations.
#
# How `terraform apply` deploys the backend:
#   1. A content hash of the image sources (Dockerfile + dep manifests + the
#      packaged cloudy/ and alembic/ trees) becomes the image label, so any
#      backend change yields a new tag. terraform_data.image_push (re)builds and
#      pushes that tag exactly when the hash moves; an unchanged tree is a no-op.
#   2. terraform_data.migrate runs `cloudy migrate` (alembic upgrade head) against
#      Neon BEFORE the new image serves, so the schema is ready first. Idempotent.
#   3. fly_machine.api points at the hashed tag with NO ignore_changes — Terraform
#      is the only thing that moves this image, so apply rolls the machine whenever
#      the source changes.
#
# DATABASE_URL is delivered as a machine env value sourced from the Neon module
# output (and to the migrate step's env). It carries the role password, so
# var.database_url is sensitive and never appears in code — only in (gitignored)
# state and tfvars. Keeping it on the Terraform-managed machine env (rather than
# `flyctl secrets set`) keeps Neon -> Fly a single declarative edge.

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

# Image sourcing: the tag is the base label plus a content hash of everything that
# composes the image — the Dockerfile, the dependency manifests, and the packaged
# source (cloudy/ and alembic/, mirroring the Dockerfile COPYs). Any backend change
# moves the hash, which moves the tag, which re-pushes the image and rolls the
# machine below. Only .py/.json/.mako are hashed so build leftovers (.pyc, .venv)
# can't trigger spurious rebuilds; sort() keeps the hash order-stable.
locals {
  backend_dir = abspath("${path.root}/../../backend")

  image_source_files = sort(concat(
    ["Dockerfile", "pyproject.toml", "uv.lock", "alembic.ini"],
    tolist(fileset(local.backend_dir, "cloudy/**/*.py")),
    tolist(fileset(local.backend_dir, "cloudy/**/*.json")),
    tolist(fileset(local.backend_dir, "alembic/**/*.py")),
    tolist(fileset(local.backend_dir, "alembic/**/*.mako")),
  ))

  source_hash = substr(sha256(join("", [
    for f in local.image_source_files : filesha256("${local.backend_dir}/${f}")
  ])), 0, 16)

  image_label = "${var.image_label}-${local.source_hash}"
  image_ref   = "registry.fly.io/${fly_app.this.name}:${local.image_label}"
}

# Build & push the backend image via flyctl's REMOTE builder (the provider can't
# build a Dockerfile, and no local Docker is needed): it builds backend/Dockerfile
# in Fly's infra and pushes to registry.fly.io/<app>. triggers_replace is keyed on
# the content-hash label, so the build re-runs exactly when the source changes and
# an unchanged tree re-applies to a no-op. depends_on the app so the per-app
# registry repo exists first (no MANIFEST_UNKNOWN gap). `--build-only --push`
# ONLY publishes the image — Terraform, not flyctl, owns the machine and the roll.
resource "terraform_data" "image_push" {
  triggers_replace = {
    app   = fly_app.this.name
    label = local.image_label
  }

  provisioner "local-exec" {
    # fly.toml + Dockerfile live in the backend dir; path.root is infra/terraform.
    working_dir = local.backend_dir
    command     = "flyctl deploy --build-only --push --remote-only --image-label ${local.image_label} --app ${fly_app.this.name}"
    environment = {
      FLY_API_TOKEN = var.fly_api_token
    }
  }

  depends_on = [fly_app.this]
}

# Run pending Alembic migrations against Neon BEFORE the new image takes traffic,
# so the schema is upgraded ahead of the code that needs it. This is Terraform's
# replacement for Fly's release_command: it runs `cloudy migrate` (== alembic
# upgrade head) from the local checkout — the same repo that builds the image —
# reading DATABASE_URL from the env we pass. Idempotent: a no-op when nothing is
# pending. Keyed on the same source hash as the image, so every code change
# re-checks the schema; depends_on image_push to order push -> migrate -> roll.
resource "terraform_data" "migrate" {
  triggers_replace = {
    source_hash = local.source_hash
  }

  provisioner "local-exec" {
    working_dir = local.backend_dir
    command     = "uv run cloudy migrate"
    environment = {
      DATABASE_URL = var.database_url
    }
  }

  depends_on = [terraform_data.image_push]
}

# The machine that runs the container. One machine in one region is plenty for a
# low-traffic API; add more `fly_machine` blocks (or count) to scale out.
#
# Port binding: the app's entrypoint is `cloudy serve --host 0.0.0.0 --port
# $PORT` (see backend/cloudy/cli.py; PORT is set by Fly to var.internal_port).
# We expose it on 443 (TLS) and 80 (redirected to HTTPS) via the services block.
resource "fly_machine" "api" {
  app        = fly_app.this.name
  region     = var.region
  name       = "${var.app_name}-machine"
  image      = local.image_ref
  depends_on = [terraform_data.image_push, terraform_data.migrate]

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

}

# NOTE on min_machines_running / scale-to-zero: autostop/autostart is a property
# of Fly's *proxy services* config (set in fly.toml: `min_machines_running`,
# `auto_stop_machines`). The andrewbaxter provider doesn't expose it on
# fly_machine, so var.min_machines_running is surfaced for documentation and is
# applied via backend/fly.toml at deploy time. It's wired through here so the
# value has one home (root variables) even though flyctl consumes it.
