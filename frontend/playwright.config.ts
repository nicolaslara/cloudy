import { defineConfig } from "@playwright/test";

/** Browser smokes — opt-in via `pnpm test:e2e` (not part of `pnpm test`). */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:5273",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:5273/app/",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
