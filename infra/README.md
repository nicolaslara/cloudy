# Deploy runbook — cloudy

How the deployed system is wired and how to operate it. Boring on purpose:
three managed services, one Terraform config that knows about all three. The
SPA is static; the API is a container; the database is serverless Postgres.

Terraform **describes** the infra. It does not deploy app code on every push —
that is GitHub Actions' job (CI/CD). `terraform apply` is run by hand, by the
owner, the handful of times the *shape* of the infra changes.

## Topology

```
                         terraform (coordinates all three)
                          │            │              │
              ┌───────────┘            │              └───────────┐
              ▼                        ▼                          ▼
   ┌───────────────────┐    ┌────────────────────┐    ┌────────────────────┐
   │  Cloudflare Pages │    │      Fly.io        │    │   Neon (Postgres)  │
   │   "cloudy-web"    │    │    "cloudy-api"    │    │   serverless PG    │
   │  React SPA, static│    │  FastAPI container │    │                    │
   │  (Vite build)     │    │  uvicorn on $PORT  │    │                    │
   └─────────┬─────────┘    └─────────┬──────────┘    └─────────┬──────────┘
             │   HTTPS                 │   psycopg                │
             │  fetch VITE_API_URL     │  DATABASE_URL            │
             └────────────────────────►──────────────────────────┘
        browser → SPA → https://cloudy-api.fly.dev/api/v1/* → Neon
```

- **Cloudflare Pages** serves the built SPA (`frontend/dist`). Static files, no server.
- **Fly.io** runs the FastAPI container (`cloudy serve`, uvicorn) bound to
  `0.0.0.0:$PORT`. Fly sets `PORT` (default 8080).
- **Neon** is the Postgres database. The backend reaches it via `DATABASE_URL`.
- **Terraform** (`infra/terraform/`) declares the Pages project, the Fly app,
  and the Neon project/database, and stitches their outputs together
  (e.g. Neon's connection string becomes the Fly secret `DATABASE_URL`).

The browser loads the SPA from Pages, then calls the Fly API directly over
HTTPS. In dev nothing changes: Vite's proxy forwards `/api/*` to the local
backend (see `frontend/vite.config.ts`).

## Prerequisites

Three accounts and one API token each. Tokens go in `terraform.tfvars`
(gitignored) — never in tracked files.

| Service       | Account                  | Token / value needed            | Where to get it |
|---------------|--------------------------|---------------------------------|-----------------|
| Neon          | neon.tech                | `neon_api_key`                  | Console → Account settings → API keys |
| Cloudflare    | dash.cloudflare.com      | `cloudflare_api_token`          | My Profile → API Tokens → Create Token (Pages: Edit) |
| Cloudflare    | "                        | `cloudflare_account_id`         | Any zone/Workers page → right sidebar "Account ID" |
| Fly.io        | fly.io                   | `fly_api_token`                 | `fly auth token` (or Dashboard → Account → Access Tokens) |

CLIs (only needed for day-2 ops and the initial `apply`):
[`terraform`](https://developer.hashicorp.com/terraform/install),
[`flyctl`](https://fly.io/docs/flyctl/install/) (`fly`), and optionally
[`wrangler`](https://developers.cloudflare.com/workers/wrangler/) for Pages logs.

## One-time setup (owner only)

This is the **only** place real cloud resources are created. CI never runs it.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in the four tokens above
terraform init                                  # download providers, init backend
terraform plan                                  # review what will be created
terraform apply                                 # OWNER STEP — creates real infra
```

`terraform.tfvars` is gitignored. The `.terraform.lock.hcl` provider lockfile
**is committed** (reproducible provider versions); everything else Terraform
writes (`*.tfstate`, `.terraform/`) is gitignored.

Useful outputs after apply:

```bash
terraform output backend_url       # https://cloudy-api.fly.dev
terraform output pages_url         # https://cloudy-web.pages.dev
terraform output -raw database_url # sensitive — Neon connection string
```

### Backend env the app expects (set as Fly secrets by Terraform)

- `DATABASE_URL` — `postgresql+psycopg://…` (psycopg scheme; matches
  `backend/cloudy/config.py`). Sourced from Neon's connection string.
- `PORT` — set by Fly; the container starts with `cloudy serve --host 0.0.0.0
  --port $PORT`. Do **not** hardcode 8400 (that's the local dev default).
- `CORS_ALLOW_ORIGINS` — the API must allow the Pages origin. The backend reads
  this comma-separated allow-list (e.g. `https://cloudy-web.pages.dev`);
  Terraform derives it from the Pages URL and injects it into the Fly machine
  env, so no manual step is needed.

## Migrations

Database migrations run automatically on every deploy via Fly's
**`release_command`**, which runs once against a temporary machine before the
new version takes traffic:

```toml
# fly.toml
[deploy]
  release_command = "cloudy migrate"   # == alembic upgrade head (see cli.py)
```

If the migration fails, Fly aborts the release and keeps the previous version
running. No manual migration step in normal operation.

## GitHub Actions secrets (CI/CD)

CI today (`.github/workflows/ci.yml`) only lints/tests. To add deploy jobs,
set these repository secrets (Settings → Secrets and variables → Actions):

| Secret name             | Used for |
|-------------------------|----------|
| `FLY_API_TOKEN`         | `flyctl deploy` of the backend container |
| `CLOUDFLARE_API_TOKEN`  | publish the built SPA to Pages |
| `CLOUDFLARE_ACCOUNT_ID` | target account for the Pages deploy |
| `VITE_API_URL`          | build-time API base baked into the SPA (e.g. `https://cloudy-api.fly.dev`) |

(Neon needs no CI secret — the app reaches it at runtime via the Fly
`DATABASE_URL` secret that Terraform set, and migrations run via
`release_command`.)

## How the frontend gets `VITE_API_URL`

Vite inlines `import.meta.env.VITE_API_URL` at **build time**, so it must be
present when `pnpm build` runs.

- **Dev:** unset. The API client uses relative paths and Vite's proxy forwards
  `/api/*` to `http://localhost:8400` (`frontend/vite.config.ts`).
- **Prod:** set `VITE_API_URL=https://cloudy-api.fly.dev` in the CI build env
  (or the Pages project env). The API client prefixes requests with it so the
  static SPA calls the Fly backend directly. (The client currently uses bare
  relative paths — adding the prefix is a tracked app-code change, not part of
  this runbook.)

## Day-2 operations

**Deploy a change** — push to `main`; CI builds and deploys (backend → Fly,
SPA → Pages). Manual fallback:

```bash
fly deploy --app cloudy-api                                  # backend
cd frontend && pnpm build && wrangler pages deploy dist \
  --project-name cloudy-web                                  # SPA
```

**Roll back**

```bash
fly releases --app cloudy-api                 # list versions
fly deploy --app cloudy-api --image <prev>    # or: fly releases rollback
# Pages: Cloudflare dashboard → cloudy-web → Deployments → "Rollback"
```

**View logs**

```bash
fly logs --app cloudy-api                     # backend (live tail)
wrangler pages deployment tail --project-name cloudy-web   # SPA build/edge
# Neon: query/connection logs in the Neon console
```

**Destroy** (tears down all real infra — irreversible)

```bash
cd infra/terraform && terraform destroy
```

## Guardrails

- `terraform apply` / `fly deploy` / `wrangler deploy` create real resources —
  run them deliberately, never from a scaffold-validation step.
- No real secrets in tracked files. `terraform.tfvars`, `*.tfstate`, and
  `.env.production` are gitignored; only `*.example` files are committed.
- Keep it simple: managed services, one Terraform config, boring defaults.
