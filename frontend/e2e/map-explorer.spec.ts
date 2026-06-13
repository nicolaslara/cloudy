import { expect, test, type Page } from "@playwright/test";
import { HEALTH, LIGHTNING_STROKES, STATION, SWEDEN_LIGHTNING } from "./fixtures";

async function mockMapApis(page: Page) {
  await page.route("**/api/v1/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HEALTH) }),
  );
  await page.route("**/api/v1/station?**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STATION) }),
  );
  await page.route("**/api/v1/lightning?**", (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("format") === "strokes") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(LIGHTNING_STROKES),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(SWEDEN_LIGHTNING),
    });
  });
}

test("map view loads with the shared timeline slider and visible window", async ({ page }) => {
  await mockMapApis(page);
  await page.goto("/app/?latlng=59.33,18.06");

  await page.getByRole("button", { name: "Map" }).click();
  await expect(page.getByText("Source: SMHI")).toBeVisible();
  await expect(page.locator(".map-canvas")).toBeVisible();
  await expect(page.locator(".time-range-picker-canvas")).toBeVisible();
  await expect(page.getByText(/\d{4}-\d{2}-\d{2} — \d{4}-\d{2}-\d{2}/)).toBeVisible();
  await expect(page.getByText(/2015-01-01 —/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Play" })).toHaveCount(0);
});
