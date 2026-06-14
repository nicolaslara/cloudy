import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import type { Candidate } from "../../../api/geocode";
import type { CloudPeriod } from "../api/cloud";
import type { LightningPeriod } from "../api/lightning";
import { LightningExplorer } from "./LightningExplorer";

const useEChartsMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/useECharts", () => ({
  useECharts: (
    option: unknown,
    structureKey?: string,
    onVisibleZoom?: unknown,
    debugKey?: "chart" | "timeSlider",
  ) => {
    useEChartsMock(option, structureKey, onVisibleZoom, debugKey);
    return { containerRef: { current: null }, chartRef: { current: null } };
  },
}));
vi.mock("../lib/useMapDeck", () => ({
  useMapDeck: () => ({ current: null }),
}));

const STOCKHOLM: Candidate = {
  label: "Stockholm",
  lat: 59.33,
  lon: 18.06,
  provider: "mock",
};

function cloudPoint(overrides: Partial<CloudPeriod> = {}): CloudPeriod {
  return {
    period: "2018-07",
    bucket_start: "2018-07-01T00:00:00Z",
    bucket_end: "2018-08-01T00:00:00Z",
    mean_cloud_pct: 42.5,
    min_cloud_pct: 0,
    max_cloud_pct: 100,
    p05_cloud_pct: 0,
    p50_cloud_pct: 50,
    p95_cloud_pct: 100,
    observed_count: 720,
    expected_count: 744,
    missing_count: 24,
    ...overrides,
  };
}

function lightningPoint(overrides: Partial<LightningPeriod> = {}): LightningPeriod {
  return {
    period: "2018-07",
    bucket_start: "2018-07-01T00:00:00Z",
    bucket_end: "2018-08-01T00:00:00Z",
    cg_count: 142,
    all_count: 388,
    lightning_days: 6,
    max_abs_peak_ka: 110.2,
    strongest_event_time: "2018-07-15T12:00:00Z",
    ...overrides,
  };
}

const CLOUD_RESPONSE = {
  aggregation: "auto",
  resolved_resolution: "month",
  station: { station_id: 98040, name: "Stockholm", distance_km: 4.2 },
  series: [cloudPoint()],
  meta: {
    from: "2015-01-01",
    to: "2026-06-11",
    coverage_fraction: 0.92,
    scope: "station",
    station_count: null,
    sources: ["smhi-metobs"],
    attribution: "Source: SMHI",
    generated_at: "2026-06-11T00:00:00Z",
    total_matched: 1,
    returned: 1,
    requested_aggregation: "auto",
    resolved_resolution: "month",
    mode: "aggregate",
    representation: "cloud_aggregate_month",
    target_points: 1800,
    point_count: 1,
    is_complete: true,
  },
};

const SWEDEN_CLOUD_RESPONSE = {
  ...CLOUD_RESPONSE,
  station: null,
  meta: {
    ...CLOUD_RESPONSE.meta,
    scope: "sweden",
    station_count: 8,
    representation: "cloud_sweden_aggregate_month",
  },
};

const SERIES_RESPONSE = {
  format: "series",
  aggregation: "auto",
  resolved_resolution: "month",
  spatial: { mode: "sweden" },
  series: [lightningPoint()],
  meta: {
    from: "2015-01-01",
    to: "2026-06-11",
    sources: ["smhi-lightning"],
    attribution: "Source: SMHI",
    generated_at: "2026-06-11T00:00:00Z",
    total_matched: 1,
    returned: 1,
    requested_aggregation: "auto",
    resolved_resolution: "month",
    mode: "aggregate",
    representation: "lightning_aggregate_month",
    target_points: 1800,
    point_count: 1,
    is_complete: true,
  },
};

function renderExplorer(
  selected: Candidate | null = null,
  presentation: "chart" | "map" = "chart",
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <LightningExplorer selected={selected} presentation={presentation} />
      </QueryClientProvider>,
    ),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  useEChartsMock.mockClear();
});

test("renders Sweden-wide without a selected location", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/api/v1/exploration/cloud")) {
      return new Response(JSON.stringify(SWEDEN_CLOUD_RESPONSE), { status: 200 });
    }
    return new Response(JSON.stringify(SERIES_RESPONSE), { status: 200 });
  });

  renderExplorer(null);
  expect(await screen.findByText(/showing sweden-wide totals/i)).toBeInTheDocument();
  expect(await screen.findByText(/sweden-wide station aggregate/i)).toBeInTheDocument();
  expect(await screen.findByText("Source: SMHI")).toBeInTheDocument();
});

test("requests series format with Sweden scope when no location is selected", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/exploration/cloud")) {
        return new Response(JSON.stringify(SWEDEN_CLOUD_RESPONSE), { status: 200 });
      }
      return new Response(JSON.stringify(SERIES_RESPONSE), { status: 200 });
    });

  renderExplorer(null);
  await screen.findByText("Source: SMHI");

  const lightningUrl = String(
    fetchMock.mock.calls.find(([input]) => String(input).includes("/api/v1/exploration/lightning?"))?.[0],
  );
  expect(lightningUrl).toContain("format=series");
  expect(lightningUrl).toContain("aggregation=auto");
  expect(lightningUrl).not.toContain("granularity=");
  expect(lightningUrl).not.toContain("lat=");
  const cloudUrl = String(
    fetchMock.mock.calls.find(([input]) => String(input).includes("/api/v1/exploration/cloud"))?.[0],
  );
  expect(cloudUrl).toContain("/api/v1/exploration/cloud");
  expect(cloudUrl).not.toContain("lat=");
  expect(cloudUrl).not.toContain("lon=");
});

test("chart controls expose only safe aggregations", async () => {
  const fetchMock = mockLightningAndCloud();

  renderExplorer(null);
  await screen.findByText("Source: SMHI");

  const group = screen.getByRole("group", { name: "Group by" });
  expect(within(group).getByRole("button", { name: "Auto" })).toBeInTheDocument();
  expect(within(group).getByRole("button", { name: "Weekly" })).toBeInTheDocument();
  expect(within(group).getByRole("button", { name: "Monthly" })).toBeInTheDocument();
  expect(within(group).getByRole("button", { name: "Yearly" })).toBeInTheDocument();
  expect(within(group).queryByRole("button", { name: "Daily" })).not.toBeInTheDocument();
  expect(within(group).queryByRole("button", { name: "Hourly" })).not.toBeInTheDocument();

  for (const label of ["Weekly", "Monthly", "Yearly", "Auto"]) {
    await userEvent.click(within(group).getByRole("button", { name: label }));
  }

  await waitFor(() => {
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(4);
  });
  const aggregations = fetchMock.mock.calls
    .map(([input]) => new URL(String(input), "http://cloudy.test"))
    .filter((url) => url.pathname === "/api/v1/exploration/lightning")
    .map((url) => url.searchParams.get("aggregation"))
    .filter((value): value is string => value !== null);

  expect(new Set(aggregations)).toEqual(new Set(["auto", "week", "month", "year"]));
  expect(aggregations).not.toContain("day");
  expect(aggregations).not.toContain("hour");
  expect(aggregations).not.toContain("6h");
  expect(aggregations).not.toContain("raw");
});

test("visible range narrows auto chart query dates", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/api/v1/exploration/cloud")) {
      return new Response(JSON.stringify(CLOUD_RESPONSE), { status: 200 });
    }
    return new Response(
      JSON.stringify({
        ...SERIES_RESPONSE,
        resolved_resolution: "day",
        meta: { ...SERIES_RESPONSE.meta, resolved_resolution: "day" },
      }),
      { status: 200 },
    );
  });

  renderExplorer(null);
  await screen.findByText("Source: SMHI");
  await userEvent.click(
    within(screen.getByRole("group", { name: "Visible range" })).getByRole("button", {
      name: "1 week",
    }),
  );

  await waitFor(() => {
    const urls = fetchMock.mock.calls
      .map(([input]) => new URL(String(input), "http://cloudy.test"))
      .filter(
        (url) =>
          url.pathname === "/api/v1/exploration/lightning" &&
          url.searchParams.get("aggregation") === "auto",
      );
    const shortRange = urls.find((url) => {
      const from = new Date(`${url.searchParams.get("from")}T00:00:00Z`);
      const to = new Date(`${url.searchParams.get("to")}T00:00:00Z`);
      const days = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
      return days <= 7;
    });
    expect(shortRange).toBeDefined();
    const from = new Date(`${shortRange!.searchParams.get("from")}T00:00:00Z`);
    const to = new Date(`${shortRange!.searchParams.get("to")}T00:00:00Z`);
    const days = Math.round((to.getTime() - from.getTime()) / 86_400_000) + 1;
    expect(days).toBeLessThanOrEqual(7);
  });
});

test("unified cloud query aligns to resolved lightning resolution", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/api/v1/exploration/cloud")) {
      return new Response(JSON.stringify({ ...CLOUD_RESPONSE, resolved_resolution: "day" }), {
        status: 200,
      });
    }
    return new Response(
      JSON.stringify({
        ...SERIES_RESPONSE,
        resolved_resolution: "day",
        meta: { ...SERIES_RESPONSE.meta, resolved_resolution: "day" },
      }),
      { status: 200 },
    );
  });

  renderExplorer(STOCKHOLM);
  await screen.findByText("Source: SMHI");

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        ([input]) =>
          String(input).includes("/api/v1/exploration/cloud") &&
          String(input).includes("aggregation=day"),
      ),
    ).toBe(true);
  });
});

test("dragging the shared time slider marks the visible range as custom", async () => {
  mockLightningAndCloud();

  renderExplorer(null);
  await screen.findByText("Source: SMHI");

  const timeSliderCall = [...useEChartsMock.mock.calls]
    .reverse()
    .find((call) => call[3] === "timeSlider");
  expect(timeSliderCall).toBeDefined();

  act(() => {
    timeSliderCall![2]({ startPeriod: "2015-01", endPeriod: "2026-06" });
  });

  const group = screen.getByRole("group", { name: "Visible range" });
  expect(within(group).getByRole("button", { name: "Custom" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByText("2015-01-01 — 2026-06-30")).toBeInTheDocument();
});

function mockLightningAndCloud(lightningBody = SERIES_RESPONSE) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/api/v1/exploration/cloud")) {
      return new Response(
        JSON.stringify(url.includes("lat=") ? CLOUD_RESPONSE : SWEDEN_CLOUD_RESPONSE),
        { status: 200 },
      );
    }
    return new Response(JSON.stringify(lightningBody), { status: 200 });
  });
}

function lastChartStructureKey(): string | undefined {
  return [...useEChartsMock.mock.calls]
    .reverse()
    .find((call) => call[3] === "chart")?.[1];
}

test("requests radius filter when a location is selected", async () => {
  const fetchMock = mockLightningAndCloud({
    ...SERIES_RESPONSE,
    spatial: { mode: "radius", lat: 59.33, lon: 18.06, radius_km: 10 },
  } as typeof SERIES_RESPONSE & {
    spatial: { mode: string; lat: number; lon: number; radius_km: number };
  });

  renderExplorer(STOCKHOLM);
  await screen.findByText("Source: SMHI");

  const url = String(fetchMock.mock.calls[0]?.[0]);
  expect(url).toContain("lat=59.33");
  expect(url).toContain("lon=18.06");
  expect(url).toContain("radius_km=10");
});

test("toggling radius refetches with 25 km", async () => {
  const fetchMock = mockLightningAndCloud();

  renderExplorer(STOCKHOLM);
  await screen.findByText("Source: SMHI");
  await userEvent.click(screen.getByRole("button", { name: "25 km" }));

  expect(
    fetchMock.mock.calls.some(([input]) => String(input).includes("radius_km=25")),
  ).toBe(true);
});

test("location change does not change the chart structure key", async () => {
  mockLightningAndCloud();

  const { rerender, client } = renderExplorer(STOCKHOLM);
  await screen.findByText("Source: SMHI");
  const structureKeyBefore = lastChartStructureKey();

  rerender(
    <QueryClientProvider client={client}>
      <LightningExplorer
        selected={{ ...STOCKHOLM, lat: 57.71, lon: 11.97, label: "Göteborg" }}
        presentation="chart"
      />
    </QueryClientProvider>,
  );
  await screen.findByText("Source: SMHI");
  const structureKeyAfter = lastChartStructureKey();

  expect(structureKeyBefore).toBeDefined();
  expect(structureKeyAfter).toBe(structureKeyBefore);
});

test("map presentation hides granularity controls", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response(JSON.stringify(SERIES_RESPONSE), { status: 200 }),
  );

  renderExplorer(null, "map");
  await screen.findByText(/each dot is one strike/i);

  expect(screen.queryByRole("group", { name: "Group by" })).not.toBeInTheDocument();
});

test("map presentation uses the shared radius control", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("format=strokes")) {
      return new Response(
        JSON.stringify({
          format: "strokes",
          columns: ["lon", "lat", "peak_ka", "cg", "ts"],
          rows: [],
          spatial: { mode: "radius", lat: 59.33, lon: 18.06, radius_km: 25 },
          meta: {
            from: "2015-01-01",
            to: "2026-06-11",
            sources: ["smhi-lightning"],
            attribution: "Source: SMHI",
            generated_at: "2026-06-11T00:00:00Z",
          },
        }),
        { status: 200 },
      );
    }
    return new Response(JSON.stringify(SERIES_RESPONSE), { status: 200 });
  });

  renderExplorer(STOCKHOLM, "map");
  await screen.findByText("Source: SMHI");
  await userEvent.click(screen.getByRole("button", { name: "25 km" }));

  expect(
    (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.some(([input]) =>
      String(input).includes("format=strokes") && String(input).includes("radius_km=25"),
    ),
  ).toBe(true);
});

test("shows an error state when the API fails", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 500 }));

  renderExplorer(null);
  expect(
    await screen.findByText(/could not load history/i),
  ).toBeInTheDocument();
});
