# Deploy runbook — cloudy

How the deployed system is wired and how to operate it. Boring on purpose:
three managed services, one Terraform config that knows about all three. The
SPA is static; the API is a container; the database is serverless Postgres.

Clear split of duties. **Terraform provisions** the cloud topology — the Neon
project, the Fly **app + IPs**, the Pages **project**, and the R2 bucket — and is
run by hand by the owner. **CI ships app code** on every green push to `main`
(`deploy.yml` builds + rolls the backend on Fly and builds + uploads the SPA to
Pages). So a code push can deploy the app but never mutates infra, and changing
cloud topology is a deliberate `terraform apply`. GitHub Actions also runs tests
(`ci.yml`) and the scheduled data refresh (`ingest.yml`).

## Topology

```
                         terraform (provisions all three)
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
- **Terraform** (`infra/terraform/`) declares the Pages project, the Fly app + IPs,
  the Neon project/database, and the R2 raw archive bucket. Its outputs feed the
  runtime wiring (e.g. Neon's connection string is set as the Fly `DATABASE_URL`
  secret — see [Backend runtime secrets](#backend-runtime-secrets-on-fly-not-github)).

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

The org token above is for Terraform only. CI deploys the app on every green push
to `main` and uses its **own** app-scoped Fly deploy token
(`fly tokens create deploy -a cloudy-api`), stored as the `FLY_API_TOKEN` Actions
secret — never the org token. See
[GitHub Actions secrets](#github-actions-secrets-cicd).

**Enable R2 first.** Terraform creates an R2 bucket for the raw archive, but R2
is an opt-in product: open the Cloudflare dashboard → R2 once and accept the
terms, or `terraform apply` fails creating the bucket. (No card needed for the
free tier; R2 just has to be activated on the account.)

CLIs: `terraform apply` itself only needs
[`terraform`](https://developer.hashicorp.com/terraform/install) on `PATH` — it
talks to the provider APIs and no longer shells out to build or deploy anything.
The app-deploy CLIs ([`flyctl`](https://fly.io/docs/flyctl/install/) for the
backend, Node's `pnpm` + `wrangler` for the SPA, and
[`uv`](https://docs.astral.sh/uv/) for `cloudy migrate`) run in CI (`deploy.yml`);
you only need them locally for a manual deploy or the one-time backfill.

## One-time setup (owner only)

This is the **only** place real cloud resources are created. CI never runs it.
`terraform apply` stands up the cloud topology — the Neon project, the Fly **app +
IPs**, the Pages **project**, and the R2 bucket. It does **not** build an image or
create a machine; the first backend machine (and the first SPA upload) come from a
deploy.

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # fill in tokens + neon_org_id
terraform init                                  # download providers, init backend
terraform plan                                  # review what will be created
terraform apply                                 # OWNER STEP — creates real infra
```

Then bring up the application. CI does all of this on every push to `main`; the
manual equivalents below are for the very first deploy:

1. Set the backend runtime secrets on Fly — the pooled `DATABASE_URL` and
   `CORS_ALLOW_ORIGINS` (see [Backend runtime secrets](#backend-runtime-secrets-on-fly-not-github)).
2. Deploy the backend from `backend/`: `flyctl deploy --remote-only` — builds
   `backend/Dockerfile`, runs `cloudy migrate` as the fly.toml `release_command`,
   then creates/rolls the machine. (The machine never boots a missing image
   because the build, migrate, and roll happen in one step.)
3. Deploy the SPA from `frontend/`: `pnpm install --frozen-lockfile && pnpm build`,
   then `npx wrangler@4 pages deploy dist --project-name=cloudy-web --branch=main`,
   with `VITE_API_URL` set to the backend URL.

Or just push to `main` (or `gh workflow run deploy.yml`) and let CI do all three.

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

### Backend env the app expects (Fly app secrets)

- `DATABASE_URL` — `postgresql+psycopg://…` (psycopg scheme; matches
  `backend/cloudy/config.py`), the **pooled** Neon URL. Set as a Fly app secret.
- `PORT` — set by Fly; the container starts with `cloudy serve --host 0.0.0.0
  --port $PORT`. Do **not** hardcode 8400 (that's the local dev default).
- `CORS_ALLOW_ORIGINS` — the API must allow the Pages origin. The backend reads
  this comma-separated allow-list (e.g. `https://cloudy-web.pages.dev`), set as a
  Fly app secret (see [Backend runtime secrets](#backend-runtime-secrets-on-fly-not-github)).

Both are Fly **app secrets** (not Terraform-managed machine env), so they persist
across every `flyctl deploy` and are injected into each machine.

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

(Backend deploys also run `cloudy migrate` automatically as the Fly
`release_command`, so this is idempotent — but running it explicitly here against
the **direct** endpoint is the simplest way to get the schema in place before the
backfill, even before the first deploy. See [Migrations](#migrations).)

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

Database migrations run automatically on every backend deploy as the Fly
**`release_command`** (`backend/fly.toml`: `release_command = "cloudy migrate"`).
On each `flyctl deploy` (i.e. every green push to `main`) Fly runs `cloudy migrate`
(== `alembic upgrade head`) against Neon in a one-off release machine **before** the
new image is rolled out, so the schema is upgraded ahead of the code that needs it.
It's idempotent — a no-op when nothing is pending.

If the release command fails, Fly aborts the deploy and the previous version keeps
serving. No manual migration step in normal operation; the explicit `cloudy migrate`
in [First production setup](#first-production-setup) is only for seeding the schema
before the initial backfill.

## GitHub Actions secrets (CI/CD)

Three workflows live in `.github/workflows/`. **App code** ships from CI; **infra**
(cloud topology) is still applied by hand via `terraform apply`, which holds the
local state — a code push can build and roll the app but never mutate infra.

- **`ci.yml`** — lint/typecheck/test on every PR and push. No secrets.
- **`deploy.yml`** — on every green push to `main` (and manual dispatch): re-runs
  the full test suite, then builds + ships the backend image to Fly and the SPA to
  Cloudflare Pages. Migrations run as the Fly `release_command`, not in the job.
- **`ingest.yml`** — scheduled/manual data refresh (incremental or smoke).

Set these repository secrets (Settings → Secrets and variables → Actions):

| Secret name             | Used by         | Value |
|-------------------------|-----------------|-------|
| `FLY_API_TOKEN`         | deploy          | App-scoped Fly **deploy** token: `fly tokens create deploy -a cloudy-api`. Store the full `FlyV1 …` value — not the Terraform org token. |
| `VITE_API_URL`          | deploy          | Public backend origin baked into the SPA build — `https://cloudy-api.fly.dev` (`terraform output -raw backend_url`). |
| `CLOUDFLARE_API_TOKEN`  | deploy, ingest  | Cloudflare token with Pages:Edit (deploy) and Workers R2 Storage:Edit (ingest archive). The same token from `terraform.tfvars` works. |
| `CLOUDFLARE_ACCOUNT_ID` | deploy, ingest  | Account that owns the Pages project and R2 bucket. |
| `DATABASE_URL`          | ingest          | Neon **direct** (non-pooled) URL — `terraform output -raw database_url_direct`. The refresh job runs a backtest and bulk upserts, so it wants the direct endpoint, same as the manual backfill. |

Repository variables:

| Variable name        | Used by | Value |
|----------------------|---------|-------|
| `RAW_ARCHIVE_BUCKET` | ingest  | R2 bucket name for the `data/raw` archive (defaults to `cloudy-raw`). |

The running app reaches Neon via the pooled `DATABASE_URL`, and its CORS origin via
`CORS_ALLOW_ORIGINS` — both are **Fly app secrets** (`fly secrets set`), not GitHub
secrets: Fly injects them into every machine and preserves them across `flyctl
deploy`, so a CI roll never drops them. Migrations apply on each release via the
`release_command`. The ingest workflow is a separate operator job, so it carries
its own (direct) Neon URL as a *repository* secret rather than reusing the app's
pooled one. Deploy/ingest repo credentials live as Actions secrets (above); the
broader Terraform credentials (Neon API key, Fly **org** token) stay in
`terraform.tfvars` and never enter CI.

### Backend runtime secrets (on Fly, not GitHub)

Set once on the app; they survive every deploy:

```bash
fly secrets set \
  DATABASE_URL="$(cd infra/terraform && terraform output -raw database_url)" \
  CORS_ALLOW_ORIGINS="https://cloudy-web.pages.dev" \
  -a cloudy-api
```

`DATABASE_URL` here is the **pooled** Neon URL (what the app uses); the direct URL
is only for bulk/ingest jobs. Rotate these here if the Neon credentials change.

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

**Deploy app code** — push to `main`; `deploy.yml` re-runs the tests, then builds
the backend image, runs migrations (Fly `release_command`), rolls the Fly machine,
and ships the SPA to Pages (use `workflow_dispatch` to re-run a deploy by hand).
This is the path that rolls the backend.

**Change infra** — run `terraform apply` for cloud topology (Neon, the Pages
project, R2, the Fly app + IPs). Only needs `terraform` on `PATH` and the tokens in
`terraform.tfvars`; it no longer builds or deploys app code, so a clean checkout
plans as **no changes**. Scope a tier with `-target=module.frontend_pages`,
`-target=module.neon`, etc.

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

**Roll back** — the durable way is to revert the offending commit and push; CI
redeploys the now-previous code. For a fast manual revert without changing code:

```bash
# Backend — redeploy a prior image (flyctl tags each deploy):
fly releases --app cloudy-api                 # deploy history + image refs
fly deploy --app cloudy-api -c backend/fly.toml --image registry.fly.io/cloudy-api:<prev-tag>
# Pages: Cloudflare dashboard → cloudy-web → Deployments → "Rollback"
```

A manual image rollback sticks until the next push to `main` redeploys current
code, so land the code revert too if the rollback should be permanent.

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

- `terraform apply` creates real cloud resources — run it deliberately, never from
  a scaffold-validation step. Use `terraform plan` first.
- No real secrets in tracked files. `terraform.tfvars`, `*.tfstate`, and
  `.env.production` are gitignored; only `*.example` files are committed.
- Keep it simple: managed services, one Terraform config, boring defaults.
