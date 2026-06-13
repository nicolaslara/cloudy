import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev-only proxy: the SPA calls /api/v1/*, and the FastAPI backend serves the
// same paths (router prefix /api/v1), so requests pass through unrewritten.
// appType "mpa" disables SPA fallback: only the /app/ entry exists,
// so the root presentation page can be added separately later.
export default defineConfig({
  appType: "mpa",
  plugins: [react()],
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
