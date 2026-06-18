# Deploy runbook — cloudy

How the deployed system is wired and how to operate it. Boring on purpose:
three managed services, one Terraform config that knows about all three. The
SPA is static; the API is a container; the database is serverless Postgres.

Terraform owns **both** the infra and the deploy: `terraform apply` provisions the
three services *and* ships app code — it builds and rolls the backend image (plus
migrations) and builds and uploads the SPA. There is no push-to-deploy pipeline;
apply is run by hand, by the owner. GitHub Actions only runs tests (`ci.yml`) and
the scheduled data refresh (`ingest.yml`).

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
- **Cloudflare R2** stores a compressed copy of the gitignored `data/raw`
  archive so scheduled ingestion can replay raw SMHI files before downloading
  anything missing.
- **Terraform** (`infra/terraform/`) declares the Pages project, the Fly app,
  the Neon project/database, and the R2 raw archive bucket, and stitches their outputs together
  (e.g. Neon's connection string becomes the Fly secret `DATABASE_URL`).

The browser loads the SPA from Pages, then calls the Fly API directly over
HTTPS. In dev nothing changes: Vite's proxy forwards `/api/*` to the local
backend (see `frontend/vite.config.ts`).

## Prerequisites

Three accounts and a handful of token/id values. They go in `terraform.tfvars`
(gitignored) — never in tracked files.

| Service    | tfvars key              | How to get it / gotcha |
|------------|-------------------------|------------------------|
| Neon       | `neon_api_key`          | Console → Account settings → API keys. |
| Neon       | `neon_org_id`           | **Required** for the current Neon default (org-scoped API keys): the project must be created under an org. Get it from `GET https://console.neon.tech/api/v2/users/me/organizations` (or Console → Organization settings). Legacy personal accounts can leave it empty. |
| Cloudflare | `cloudflare_api_token`  | My Profile → API Tokens → Create Token. Needs **Account → Workers R2 Storage : Edit** *and* **Account → Cloudflare Pages : Edit** (plus Zone → DNS : Edit only if you set a custom domain). |
| Cloudflare | `cloudflare_account_id` | Any zone/Workers page → right sidebar "Account ID". |
| Fly.io     | `fly_api_token`         | **Use `fly tokens create org -o <org> -n cloudy-terraform`**, not `fly auth token` — see below. |

**Why an org token for Fly (not `fly auth token`).** The andrewbaxter/fly
Terraform provider talks to Fly's GraphQL API and needs to *read the org* to
create the app. `fly auth token` mints a short-lived personal macaroon that the
provider rejects for those org-scoped queries (and it expires mid-deploy). A
long-lived org token works for everything Terraform does:

```bash
fly tokens create org -o personal -n cloudy-terraform -x 8760h
# Store the value WITHOUT the leading "FlyV1 " prefix in terraform.tfvars.
```

The same org token is the only Fly credential needed — CI does not deploy, so
there is no separate app-scoped deploy token. See
[GitHub Actions secrets](#github-actions-secrets-cicd).

**Enable R2 first.** Terraform creates an R2 bucket for the raw archive, but R2
is an opt-in product: open the Cloudflare dashboard → R2 once and accept the
terms, or `terraform apply` fails creating the bucket. (No card needed for the
free tier; R2 just has to be activated on the account.)

CLIs `terraform apply` shells out to (so they must be installed and on `PATH`
wherever you apply): [`terraform`](https://developer.hashicorp.com/terraform/install),
[`flyctl`](https://fly.io/docs/flyctl/install/) (`fly`, image build),
[`uv`](https://docs.astral.sh/uv/) (runs `cloudy migrate`), and Node's
`pnpm` + `npx` (SPA build + `wrangler` upload). `wrangler` itself is fetched via
`npx`, so no global install is required.

## One-time setup (owner only)

This is the **only** place real cloud resources are created. CI never runs it.
One `terraform apply` stands up everything, including the first backend image:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in tokens + neon_org_id
terraform init                                  # download providers, init backend
terraform plan                                  # review what will be created
terraform apply                                 # OWNER STEP — creates real infra
```

**`flyctl` must be installed and on `PATH`**: the andrewbaxter/fly provider can't
build a Dockerfile, so the `backend_fly` module shells out to flyctl's **remote
builder** (no local Docker needed) to build `backend/Dockerfile` and push it to
`registry.fly.io/cloudy-api`. Terraform sequences this for you inside the single
apply — create the Fly app → build & push the image → create the machine from it
— which is why a machine never tries to boot a missing image. The build runs once
per state; re-applies don't rebuild.

Every later apply rolls the backend the same way: Terraform hashes the backend
sources into the image tag, so any code change rebuilds + pushes a new image, runs
`cloudy migrate` against Neon, and rolls the machine onto it — no out-of-band
`flyctl deploy`. `backend_image_label` is only the tag *prefix*; the hash, not you,
bumps the tag per release. Both `flyctl` and `uv` must be on `PATH` for apply.

`terraform.tfvars` is gitignored. The `.terraform.lock.hcl` provider lockfile
**is committed** (reproducible provider versions); everything else Terraform
writes (`*.tfstate`, `.terraform/`) is gitignored.

Useful outputs after apply:

```bash
terraform output backend_url            # https://cloudy-api.fly.dev
terraform output pages_url              # https://cloudy-web.pages.dev
terraform output raw_archive_bucket     # cloudy-raw
terraform output -raw database_url      # sensitive — pooled Neon URL (the app uses this)
terraform output -raw database_url_direct # sensitive — direct Neon URL (use for backfill)
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

## First production setup

Infra is up but empty. Two explicit operator steps remain — apply the schema,
then load the data. Both run from your **workstation**, not Fly or CI: the
backfill replays your **local** `data/raw` archive (no SMHI re-download), and
only your machine has it.

All of these point `DATABASE_URL` at Neon's **direct** endpoint, not the pooled
one the app uses. A multi-million-row load holds one long transaction, and the
pgBouncer pooler will sever it mid-COPY; the direct compute endpoint holds the
single long connection the backfill needs.

1. Apply the schema:

```bash
cd backend
export DATABASE_URL="$(cd ../infra/terraform && terraform output -raw database_url_direct)"
uv run cloudy migrate          # alembic upgrade head
```

(`terraform apply` already ran `cloudy migrate` against the *pooled* URL as part
of the deploy, so the schema is in place. This explicit step is only here because
the backfill below wants the **direct** endpoint anyway — running migrate again
against it is a harmless no-op. See [Migrations](#migrations).)

1. Load the data (replays `data/raw`; no network fetch for archived files):

```bash
# still in backend/, with the direct DATABASE_URL exported above
export RAW_DATA_DIR=../data/raw
uv run cloudy ingest-production full
```

`full` loads every lightning day (2015 → today), all ~109 active cloud stations
and their rollups, the Sweden-wide Normals, and the weekly-outlook backtest
artifact — roughly 22M rows / several GB over the network, so budget tens of
minutes. Bursting Neon compute helps a lot (see [Neon plan & sizing](#neon-plan--sizing)).
The job survives transient Neon disconnects: each unit (one lightning day, one
cloud station) is its own idempotent transaction and is retried on a dropped
connection.

1. Upload the local raw archive to R2 so scheduled CI refreshes start from the
same cache:

```bash
cd ..
scripts/raw-archive.sh upload
```

For a quick smoke before the full backfill (one month of lightning + one cloud
station):

```bash
cd backend && uv run cloudy ingest-production smoke
```

Ingest commands can be re-run safely: station rows are upserted, cloud rows are
replaced per station/timestamp, and lightning rows are replaced per day.

### Neon plan & sizing

The full history does **not** fit Neon's Free plan: lightning + cloud is several
GB, and the Free plan caps storage at 512 MB (history retention counts against
it too). The free tier is fine for a `smoke` load or a short date range; the full
backfill needs a paid plan (Launch or higher). Symptom if you try anyway: ingest
fails partway with a `DiskFull` error.

Compute is a separate knob from storage. The endpoint runs at 0.25 CU and scales
to zero when idle; `neon_autoscaling_max_cu` (default `0.25`) lets it burst
higher under load. The bulk inserts and percentile rollups in the backfill are
CPU-bound, so raising it — e.g. `neon_autoscaling_max_cu = 4` in
`terraform.tfvars`, then `terraform apply` — cuts the load time substantially.
Because the minimum stays at 0.25 with scale-to-zero, a higher max costs nothing
at rest; you only pay the larger size for the minutes it is actually busy. You
can lower it again after the backfill, but leaving it is harmless.

Terraform does not run ingestion. It could run a `local-exec` provisioner, but
that would make infrastructure apply slow, non-repeatable, and coupled to
application data. Keep the initial backfill as an explicit operator action so it
can replay the local raw archive without downloading the whole history in Fly or
CI.

Ongoing refreshes are handled by `.github/workflows/ingest.yml`, which is
separate from deploy and runs only on `workflow_dispatch` or the weekly schedule.
That job ingests lightning only after the latest stored day plus `latest-months`
cloud data; it does not rerun the full historical backfill. GitHub Actions first
downloads the R2 raw archive, then restores/saves `data/raw` with
`actions/cache`, so weekly runs replay cached SMHI files and download only what
is missing. Successful refreshes upload the updated archive back to R2.

## Migrations

Database migrations run automatically on every deploy as a **Terraform step**
(`terraform_data.migrate` in the `backend_fly` module). On `terraform apply` it
runs `cloudy migrate` (== `alembic upgrade head`) from the local checkout against
Neon, ordered **before** the machine rolls onto the new image, so the schema is
upgraded ahead of the code that needs it. It's idempotent — a no-op when nothing
is pending — and keyed on the backend source hash, so it re-checks on every change.

If the migration fails, the apply stops before the machine is rolled, so the
previous version keeps serving. (`backend/fly.toml` has no `release_command` — it
exists only for the image build; the roll and migrations are Terraform's.) No
manual migration step in normal operation.

## GitHub Actions secrets (CI/CD)

Two workflows live in `.github/workflows/` (deploys are **not** in CI — they run
from the owner's workstation via `terraform apply`, which holds the local state):

- **`ci.yml`** — lint/typecheck/test on every PR and push. No secrets.
- **`ingest.yml`** — scheduled/manual data refresh (incremental or smoke).

Set these repository secrets (Settings → Secrets and variables → Actions):

| Secret name             | Used by | Value |
|-------------------------|---------|-------|
| `CLOUDFLARE_API_TOKEN`  | ingest  | Cloudflare token with Workers R2 Storage:Edit (ingest archive). The same token from `terraform.tfvars` works. |
| `CLOUDFLARE_ACCOUNT_ID` | ingest  | Account that owns the R2 bucket. |
| `DATABASE_URL`          | ingest  | Neon **direct** (non-pooled) URL — `terraform output -raw database_url_direct`. The refresh job runs a backtest and bulk upserts, so it wants the direct endpoint, same as the manual backfill. |

Repository variables:

| Variable name        | Used by | Value |
|----------------------|---------|-------|
| `RAW_ARCHIVE_BUCKET` | ingest  | R2 bucket name for the `data/raw` archive (defaults to `cloudy-raw`). |

The running app reaches Neon via the pooled `DATABASE_URL` Terraform sets on the
Fly machine, and migrations run as a Terraform step on each `apply`. The ingest
workflow is a separate operator job, so it carries its own (direct) Neon URL as a
secret rather than reusing the app's pooled one. The deploy credentials (Fly token,
Cloudflare token, `VITE_API_URL`) live only in `terraform.tfvars`, not in CI.

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

**Deploy a change** — run `terraform apply`. It hashes the backend and frontend
sources; whatever changed gets rebuilt and shipped, the rest is a no-op:

```bash
cd infra/terraform
terraform apply
# backend changed → rebuild+push image, cloudy migrate, roll the Fly machine
# frontend changed → pnpm build with VITE_API_URL, wrangler upload to Pages
```

Requires `flyctl`, `uv`, `pnpm`, and `npx` on `PATH` (apply shells out to them),
and the tokens in `terraform.tfvars`. Scope a single tier if you want with
`-target=module.backend_fly` or `-target=module.frontend_pages`.

**Refresh data** — scheduled weekly by `.github/workflows/ingest.yml`, or trigger
it manually. The workflow requires the `DATABASE_URL` repository secret,
Cloudflare credentials, and access to the `RAW_ARCHIVE_BUCKET` R2 bucket:

```bash
gh workflow run ingest.yml --ref main -f mode=incremental
gh workflow run ingest.yml --ref main -f mode=smoke
```

**Upload raw archive manually** after a local full ingest:

```bash
scripts/raw-archive.sh upload
```

**Roll back** — the durable way is to revert the offending commit and
`terraform apply` (Terraform rebuilds the now-previous source and rolls). For a
fast manual revert without changing code:

```bash
# Backend — point the machine back at a prior image tag (tags are <prefix>-<hash>):
fly image show --app cloudy-api               # current tag
fly machine list --app cloudy-api            # machine id
fly machine update <machine-id> --image registry.fly.io/cloudy-api:<prev-tag> --yes
# Pages: Cloudflare dashboard → cloudy-web → Deployments → "Rollback"
```

Note a later `terraform apply` will re-roll the machine to the tag for the current
source, so land the code revert too if the rollback should stick.

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

- `terraform apply` creates real resources and ships code (it shells out to
  flyctl/wrangler under the hood) — run it deliberately, never from a
  scaffold-validation step. Use `terraform plan` first.
- No real secrets in tracked files. `terraform.tfvars`, `*.tfstate`, and
  `.env.production` are gitignored; only `*.example` files are committed.
- Keep it simple: managed services, one Terraform config, boring defaults.
