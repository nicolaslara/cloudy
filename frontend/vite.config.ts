import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import type { Plugin } from "vite";
import react from "@vitejs/plugin-react";

// The bare domain serves the project's landing deck (a self-contained static
// presentation that links through to the live app at /app/). We keep that
// concern in the build rather than the deploy layer — no host-specific rule
// (e.g. a Cloudflare _redirects file), so Terraform/Pages config stays
// untouched. This plugin reads the standalone deck (frontend/index.html) at
// build time and emits it as dist/index.html, so / is the deck and /app/ is the
// SPA. It runs at build time only, so the dev server is left alone (where the
// same file already serves at /). The deck is fully inline — no asset graph to
// bundle — so emitting its source verbatim is correct.
function rootDeck(): Plugin {
  const deckPath = fileURLToPath(new URL("./index.html", import.meta.url));
  return {
    name: "cloudy-root-deck",
    apply: "build",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "index.html",
        source: readFileSync(deckPath, "utf8"),
      });
    },
  };
}

// Dev-only proxy: the SPA calls /api/v1/*, and the FastAPI backend serves the
// same paths (router prefix /api/v1), so requests pass through unrewritten.
// appType "mpa" disables SPA fallback: only the /app/ entry is built; the bare
// root is the landing deck emitted by rootDeck() above.
export default defineConfig({
  appType: "mpa",
  plugins: [react(), rootDeck()],
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
