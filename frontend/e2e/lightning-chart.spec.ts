import { expect, test, type Page } from "@playwright/test";
import {
  CLOUD,
  GOTHENBURG,
  HEALTH,
  LIGHTNING,
  STATION,
  STOCKHOLM,
  SWEDEN_CLOUD,
  SWEDEN_LIGHTNING,
} from "./fixtures";

async function mockAppApis(page: Page, onLightningRequest?: (url: URL) => void) {
  await page.route("**/api/v1/health", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(HEALTH) }),
  );
  await page.route("**/api/v1/geocode**", (route) => {
    const query = new URL(route.request().url()).searchParams.get("q")?.toLowerCase() ?? "";
    const candidate = query.includes("gote") || query.includes("göte") ? GOTHENBURG : STOCKHOLM;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([candidate]),
    });
  });
  await page.route("**/api/v1/station?**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(STATION),
    }),
  );
  await page.route("**/api/v1/cloud?**", (route) => {
    const url = new URL(route.request().url());
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(url.searchParams.has("lat") ? CLOUD : SWEDEN_CLOUD),
    });
  });
  await page.route("**/api/v1/lightning?**", (route) => {
    const url = new URL(route.request().url());
    onLightningRequest?.(url);
    if (url.searchParams.get("format") === "strokes") return route.continue();
    const body = seriesResponseFor(
      url.searchParams.has("lat") ? LIGHTNING : SWEDEN_LIGHTNING,
      url.searchParams.get("aggregation") ?? "auto",
      url.searchParams.get("from") ?? "2015-01-01",
      url.searchParams.get("to") ?? "2026-06-12",
    );
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

function seriesResponseFor<T extends typeof LIGHTNING | typeof SWEDEN_LIGHTNING>(
  base: T,
  aggregation: string,
  from: string,
  to: string,
) {
  const resolved = aggregation === "auto" ? autoResolution(from, to) : aggregation;
  const period =
    resolved === "hour" || resolved === "raw"
      ? "2018-07-01T00:00:00Z"
      : resolved === "day" || resolved === "week"
        ? "2018-07-02"
        : "2018-07";
  return {
    ...base,
    aggregation,
    resolved_resolution: resolved,
    series: base.series.map((point) => ({
      ...point,
      period,
      bucket_start:
        resolved === "hour" || resolved === "raw"
          ? "2018-07-01T00:00:00Z"
          : resolved === "day" || resolved === "week"
            ? "2018-07-02T00:00:00Z"
            : point.bucket_start,
      bucket_end:
        resolved === "hour" || resolved === "raw"
          ? "2018-07-01T01:00:00Z"
          : resolved === "day"
            ? "2018-07-03T00:00:00Z"
            : resolved === "week"
              ? "2018-07-09T00:00:00Z"
              : point.bucket_end,
    })),
    meta: {
      ...base.meta,
      requested_aggregation: aggregation,
      resolved_resolution: resolved,
      representation: `lightning_aggregate_${resolved}`,
    },
  };
}

function autoResolution(from: string, to: string) {
  const days =
    Math.round(
      (new Date(`${to}T00:00:00Z`).getTime() - new Date(`${from}T00:00:00Z`).getTime()) /
        86_400_000,
    ) + 1;
  if (days <= 14) return "hour";
  if (days <= 93) return "day";
  if (days <= 366) return "week";
  return "month";
}

async function selectStockholm(page: Page) {
  await page.getByLabel("Address search").fill("Stockholm");
  const suggestion = page.getByRole("option", { name: STOCKHOLM.label });
  await expect(suggestion).toBeVisible({ timeout: 5000 });
  await suggestion.click();
  await expect(page.getByText("Source: SMHI")).toBeVisible();
}

async function chartCanvas(page: Page) {
  return page.locator(".chart-canvas");
}

async function readTimeSliderDays(page: Page) {
  return page.evaluate(() => {
    const chart = (window as Window & {
      __cloudyTimeSlider?: {
        getOption: () => {
          xAxis?: { data?: string[] }[];
          dataZoom?: { type?: string; startValue?: string | number; endValue?: string | number }[];
        };
      };
    }).__cloudyTimeSlider;
    const option = chart?.getOption();
    const slider = option?.dataZoom?.find((z) => z.type === "slider");
    if (slider?.startValue == null || slider?.endValue == null) return null;
    const categories = option?.xAxis?.[0]?.data;
    const resolve = (value: string | number) => {
      if (typeof value === "string") return value.length === 7 ? `${value}-01` : value.slice(0, 10);
      if (Array.isArray(categories) && value >= 0 && value < categories.length) {
        return String(categories[value]).slice(0, 10);
      }
      return new Date(value).toISOString().slice(0, 10);
    };
    return { startDay: resolve(slider.startValue), endDay: resolve(slider.endValue) };
  });
}

test("?latlng= opens a location without searching", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?latlng=59.33,18.06");

  await expect(page.getByRole("heading", { name: "59.330°, 18.060°" })).toBeVisible();
  await expect(page.getByText("Source: SMHI")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("latlng")).toBe("59.33,18.06");
  expect(new URL(page.url()).searchParams.get("location")).toBeNull();
});

test("?location= geocodes on load", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?location=Stockholm");

  await expect(page.getByRole("heading", { name: STOCKHOLM.label })).toBeVisible();
  await expect(page.getByText("Source: SMHI")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("location")).toBe(STOCKHOLM.label);
  expect(new URL(page.url()).searchParams.get("latlng")).toBeNull();
});

test("both location= and latlng= are ignored", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?latlng=59.33,18.06&location=Stockholm");

  await expect(page.getByRole("heading", { name: STOCKHOLM.label })).toHaveCount(0);
  await expect(page.getByText(/showing sweden-wide totals/i)).toBeVisible();
});

test("explore view renders Sweden-wide without searching", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/");

  await expect(page.getByText(/showing sweden-wide totals/i)).toBeVisible();
  await expect(page.getByText(/sweden-wide station aggregate/i)).toBeVisible();
  await expect(page.getByText("Source: SMHI")).toBeVisible();
  await expect(page.locator(".chart-canvas")).toBeVisible();
});

test("lightning chart renders and survives strike scale toggles", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/");
  await selectStockholm(page);

  const canvas = await chartCanvas(page);
  await expect(canvas).toBeVisible();
  const boxBefore = await canvas.boundingBox();
  expect(boxBefore?.width ?? 0).toBeGreaterThan(100);
  expect(boxBefore?.height ?? 0).toBeGreaterThan(100);

  await page.getByRole("button", { name: "Log" }).click();
  await expect(canvas).toBeVisible();
  await expect(page.getByText(/could not load lightning history/i)).toHaveCount(0);

  await page.getByRole("button", { name: "Linear" }).click();
  const boxAfter = await canvas.boundingBox();
  expect(boxAfter?.width ?? 0).toBeGreaterThan(100);
  expect(boxAfter?.height ?? 0).toBeGreaterThan(100);
});

test("weekly aggregation opens with a zoom window and keeps it across scale changes", async ({
  page,
}) => {
  await mockAppApis(page);
  await page.goto("/app/");
  await selectStockholm(page);

  await clickAggregation(page, "week");

  const canvas = await chartCanvas(page);
  await expect(canvas).toBeVisible();

  await page.getByRole("button", { name: "Log" }).click();
  await expect(canvas).toBeVisible();
  await expect(page.getByText(/loading lightning history/i)).toHaveCount(0);
});

test("chart UI only emits safe aggregation requests", async ({ page }) => {
  const aggregations: string[] = [];
  await mockAppApis(page, (url) => {
    if (url.searchParams.get("format") === "series") {
      aggregations.push(url.searchParams.get("aggregation") ?? "");
    }
  });
  await page.goto("/app/");
  await expect(page.getByText("Source: SMHI")).toBeVisible();

  await clickAggregation(page, "week");
  await clickAggregation(page, "month");
  await clickAggregation(page, "year");
  await clickAggregation(page, "auto");

  expect(new Set(aggregations)).toEqual(new Set(["auto", "week", "month", "year"]));
  expect(aggregations).not.toContain("day");
  expect(aggregations).not.toContain("hour");
  expect(aggregations).not.toContain("6h");
  expect(aggregations).not.toContain("raw");
});

test("visible range narrows the auto chart request", async ({ page }) => {
  const requests: URL[] = [];
  await mockAppApis(page, (url) => {
    if (url.searchParams.get("format") === "series") requests.push(url);
  });
  await page.goto("/app/");
  await expect(page.getByText("Source: SMHI")).toBeVisible();

  await page
    .getByRole("group", { name: "Visible range" })
    .getByRole("button", { name: "1 week" })
    .click();

  const requestDays = (url: URL) => {
    const from = new Date(`${url.searchParams.get("from")}T00:00:00Z`);
    const to = new Date(`${url.searchParams.get("to")}T00:00:00Z`);
    return Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
  };

  await expect.poll(() => requests.some((url) => requestDays(url) <= 7)).toBe(true);
  const shortRequest = requests.find((url) => requestDays(url) <= 7);
  expect(shortRequest).toBeDefined();
  expect(requestDays(shortRequest!)).toBeLessThanOrEqual(7);
});

test("radius toggle preserves the time slider window on week view", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/");
  await selectStockholm(page);

  await clickAggregation(page, "week");

  const readSliderZoom = () =>
    page.evaluate(() => {
      const chart = (window as Window & { __cloudyTimeSlider?: { getOption: () => { dataZoom?: { type?: string; start?: number; end?: number; startValue?: string; endValue?: string }[] } } }).__cloudyTimeSlider;
      const slider = chart?.getOption().dataZoom?.find((z) => z.type === "slider");
      return slider
        ? { start: slider.start, end: slider.end, startValue: slider.startValue, endValue: slider.endValue }
        : null;
    });

  const zoomBefore = await readSliderZoom();
  expect(zoomBefore).not.toBeNull();

  await page.getByRole("group", { name: "Lightning radius" }).getByRole("button", { name: "25 km" }).click();
  await expect(page.locator(".chart-canvas")).toBeVisible();
  await expect(page.getByText(/could not load lightning history/i)).toHaveCount(0);

  expect(await readSliderZoom()).toEqual(zoomBefore);
});

const AGGREGATION_BUTTON: Record<"auto" | "week" | "month" | "year", string> = {
  auto: "Auto",
  week: "Weekly",
  month: "Monthly",
  year: "Yearly",
};

async function clickAggregation(page: Page, aggregation: "auto" | "week" | "month" | "year") {
  const button = page
    .getByRole("group", { name: "Group by" })
    .getByRole("button", { name: AGGREGATION_BUTTON[aggregation] });
  if (await button.getAttribute("aria-pressed") === "true") return;
  await Promise.all([
    page
      .waitForResponse(
        (response) =>
          response.url().includes("/api/v1/lightning") &&
          response.url().includes(`aggregation=${aggregation}`) &&
          response.ok(),
        { timeout: 5000 },
      )
      .catch(() => undefined),
    button.click(),
  ]);
  await expect(button).toHaveAttribute("aria-pressed", "true");
}

test("location change preserves the time slider window", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?latlng=59.33,18.06");
  await expect(page.getByText("Source: SMHI")).toBeVisible();

  const readSliderDays = () => readTimeSliderDays(page);

  await clickAggregation(page, "week");

  const defaultDayZoom = await readSliderDays();

  await page
    .getByRole("group", { name: "Visible range" })
    .getByRole("button", { name: "1 month" })
    .click();

  await expect.poll(readSliderDays, { timeout: 3000 }).not.toEqual(defaultDayZoom);
  const zoomBefore = await readSliderDays();

  await page.getByLabel("Address search").fill("Göteborg");
  const suggestion = page.getByRole("option", { name: GOTHENBURG.label });
  await expect(suggestion).toBeVisible({ timeout: 5000 });
  await suggestion.click();
  await expect(page.getByRole("heading", { name: GOTHENBURG.label })).toBeVisible();
  await expect(page.getByText("Source: SMHI")).toBeVisible();

  await expect.poll(readSliderDays).toEqual(zoomBefore);
});

test("aggregation toggle preserves the time slider window", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?latlng=59.33,18.06");
  await expect(page.getByText("Source: SMHI")).toBeVisible();

  // Establish week view with the visible window synced (first switch can lag).
  await clickAggregation(page, "week");
  await clickAggregation(page, "month");
  await clickAggregation(page, "week");
  await expect.poll(() => readTimeSliderDays(page)).not.toBeNull();
  const dayRangeBefore = await readTimeSliderDays(page);

  await clickAggregation(page, "month");
  await clickAggregation(page, "week");

  await expect.poll(() => readTimeSliderDays(page)).toEqual(dayRangeBefore);
});

test("switching to map keeps the shared time slider", async ({ page }) => {
  await mockAppApis(page);
  await page.goto("/app/?latlng=59.33,18.06");
  await expect(page.getByText("Source: SMHI")).toBeVisible();
  await expect(page.locator(".chart-canvas")).toBeVisible();
  await expect(page.locator(".time-range-picker-canvas")).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (window as Window & {
            __cloudyChart?: { getOption: () => { dataZoom?: { type?: string }[] } };
          }).__cloudyChart
            ?.getOption()
            .dataZoom?.filter((zoom) => zoom.type === "slider").length ?? 0,
      ),
    )
    .toBe(0);

  await page.getByRole("button", { name: "Map" }).click();
  await expect(page.locator(".map-canvas")).toBeVisible();
  await expect(page.locator(".time-range-picker-canvas")).toBeVisible();
  await expect(page.getByRole("group", { name: "Group by" })).toHaveCount(0);
});
