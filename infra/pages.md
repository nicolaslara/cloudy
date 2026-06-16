# Cloudflare Pages — `cloudy-web`

How the React SPA is built and served on Cloudflare Pages, and why the routing
is set up the way it is. This is the static half of the topology; it calls the
Fly backend (`cloudy-api`) over HTTPS.

## Build settings

Configure these in the Pages project (Settings → Builds & deployments). The
repo root is the monorepo root, so point Pages at the frontend subdirectory.

| Setting | Value |
| --- | --- |
| Framework preset | None (plain Vite — no preset needed) |
| Root directory | `frontend` |
| Build command | `pnpm build` |
| Build output directory | `dist` |
| Node version | 24+ (matches `frontend/package.json` `engines`) |

`pnpm build` runs `tsc --noEmit && vite build` (see `package.json`), so the type
gate runs in CI before any bundle is emitted — a type error fails the deploy.

## Build environment variables

| Variable | Value | Why |
| --- | --- | --- |
| `VITE_API_URL` | `https://cloudy-api.fly.dev` | Origin of the deployed FastAPI backend. Inlined into the bundle at build time (Vite inlines `VITE_*`), so the SPA calls `${VITE_API_URL}/api/v1/...` cross-origin. |

Set `VITE_API_URL` only in the **Production** (and Preview, if used) build
environment. Locally it stays unset — see "API base selection" below.
`frontend/.env.production.example` documents the value; do not commit a real
`.env.production`.

Because the SPA calls a cross-origin API in prod, the backend must allow the
Pages origin via CORS. That is the backend/deploy agent's concern, not this doc.

## API base selection (one constant)

All HTTP goes through `getJson`/`postJson` in `frontend/src/api/client.ts`, which
prefixes every root-relative path (`/api/v1/...`) with a single `API_BASE`:

```ts
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
```

- **Dev:** `VITE_API_URL` is unset → `API_BASE` is `""` → requests stay
  same-origin and the Vite dev proxy (`vite.config.ts`, `/api → localhost:8400`)
  forwards them to the local FastAPI.
- **Prod:** `VITE_API_URL` is the Fly URL → requests go to
  `https://cloudy-api.fly.dev/api/v1/...`.

No call site changed — the host is decided in exactly one place.

## Routing / SPA fallback — none needed

This frontend is a **multi-page app**, not a client-side-routed SPA
(`vite.config.ts` sets `appType: "mpa"`; there is no router dependency). The
build emits two real HTML files:

- `dist/index.html` — the narrative landing deck (`/`)
- `dist/app/index.html` — the React app (`/app/`)

Cloudflare Pages serves these as static files by path, and `/app/` resolves to
`/app/index.html` automatically. There is **no** client-side route table that
needs a catch-all rewrite, so we deliberately do **not** add a
`public/_redirects` with `/* /index.html 200`: that would shadow `/app/` and
serve the landing deck for every path. If a future change introduces in-app
client-side routing under `/app/`, add a scoped rule then
(`/app/* /app/index.html 200`) — not a blanket root catch-all.
