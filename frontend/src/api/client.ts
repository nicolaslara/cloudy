// Tiny typed fetch wrapper for the JSON backend. Everything goes through
// getJson/postJson so HTTP failures surface as one error type (ApiError) that
// the UI can branch on — react-query treats a thrown ApiError as the query
// error, and apiErrorMessage maps its status to user-facing copy.

// Single source of truth for where the backend lives. Every call site passes a
// root-relative path (`/api/v1/...`); we prefix it with this base so the choice
// of host is made in exactly one place.
//
//   dev  → "" (relative). Requests stay same-origin and the Vite dev proxy
//          (vite.config.ts) forwards /api to the local FastAPI on :8400.
//   prod → VITE_API_URL, baked in at build time (e.g. the Fly backend URL), so
//          the static SPA on Pages talks cross-origin to the deployed API.
//
// Trailing slashes are stripped so `${API_BASE}${path}` never doubles the `/`.
const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

// Join the base to a root-relative API path. Kept tiny and pure so both helpers
// share identical URL construction.
function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

// Carries the HTTP status alongside the message so callers can distinguish
// "bad input" (4xx) from "backend down" (5xx) without re-parsing the message,
// and keeps the parsed JSON body (when there is one) in `detail` for context.
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(apiUrl(path), { headers: { Accept: "application/json" } });
  if (!res.ok) {
    throw new ApiError(res.status, `GET ${path} returned ${res.status}`, await errorDetail(res));
  }
  return res.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new ApiError(res.status, `POST ${path} returned ${res.status}`, await errorDetail(res));
  }
  return res.json() as Promise<T>;
}

// Best-effort extraction of the error body for diagnostics — never throws, so a
// non-JSON or unreadable error response degrades to `undefined` rather than
// masking the original HTTP failure we actually want to report.
async function errorDetail(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return undefined;
  try {
    return await res.json();
  } catch {
    return undefined;
  }
}
