import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";

// Until a real landing page ships at /, the bare domain still needs *something*
// so a static host doesn't answer the root with a 404. We keep that concern in
// the build rather than the deploy layer — no host-specific rule (e.g. a
// Cloudflare _redirects file), so Terraform/Pages config stays untouched. Instead
// this plugin emits a tiny dist/index.html that client-side redirects to /app/.
// It runs at build time only, so the dev server is left alone and a local root
// page (if present) still serves at /. Drop this plugin when a real page lands at /.
function rootRedirect(): Plugin {
  const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>cloudy</title>
    <meta http-equiv="refresh" content="0; url=/app/" />
    <link rel="canonical" href="/app/" />
    <script>
      // Preserve any ?query/#hash so deep links survive the hop to /app/.
      location.replace("/app/" + location.search + location.hash);
    </script>
  </head>
  <body>Redirecting to <a href="/app/">/app/</a>&hellip;</body>
</html>
`;
  return {
    name: "cloudy-root-redirect",
    apply: "build",
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "index.html", source: html });
    },
  };
}

// Dev-only proxy: the SPA calls /api/v1/*, and the FastAPI backend serves the
// same paths (router prefix /api/v1), so requests pass through unrewritten.
// appType "mpa" disables SPA fallback: only the /app/ entry is built; the bare
// root is the redirect emitted above (a real root page can be added later).
export default defineConfig({
  appType: "mpa",
  plugins: [react(), rootRedirect()],
  build: { rollupOptions: { input: { app: "app/index.html" } } },
  optimizeDeps: { include: ["maplibre-gl", "@deck.gl/core", "@deck.gl/layers", "@deck.gl/mapbox"] },
  server: {
    port: 5273, // 5173 is taken on this machine; strictPort keeps docs honest
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://localhost:8400",
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
