import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Dev-only proxy: the SPA calls /api/v1/*, and the FastAPI backend serves the
// same paths (router prefix /api/v1), so requests pass through unrewritten.
export default defineConfig({
  appType: "mpa",
  plugins: [react()],
  build: { rollupOptions: { input: { app: "app/index.html" } } },
  server: {
    port: 5273,
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
  },
});
