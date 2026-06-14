import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Candidate } from "../../api/geocode";
import { NormalsView } from "./NormalsView";

// Mount the chart through a stub: jsdom has no canvas layout, and these tests are
// about the view's composition (prompt, controls, callouts, charts mounting),
// not ECharts itself. We assert the option reaches the renderer.
const useChartMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/useChart", () => ({
  useChart: (option: unknown, structureKey?: string) => {
    useChartMock(option, structureKey);
    return { containerRef: { current: null }, chartRef: { current: null } };
  },
}));

const STOCKHOLM: Candidate = { label: "Stockholm", lat: 59.33, lon: 18.06, provider: "mock" };

const CLOUD_RESPONSE = {
  scope: "station",
  station: { station_id: 98040, name: "Stockholm-Bromma", distance_km: 4.2 },
  station_count: null,
  period: "month",
  series: [
    {
      period: "7",
      mean_cloud_pct: 55,
      p10_cloud_pct: 20,
      p50_cloud_pct: 55,
      p90_cloud_pct: 85,
      clear_pct: 30,
      partial_pct: 25,
      overcast_pct: 45,
      observed_count: 1000,
      year_count: 10,
    },
  ],
  current_month: {
    month: 7,
    observed_so_far_pct: 50,
    observed_days: 10,
    climatology_tail_pct: 60,
    expected_pct: 58,
    baseline_pct: 52,
  },
  meta: { sources: ["smhi-metobs"], attribution: "Source: SMHI", generated_at: "x", year_count: 10 },
};

const LIGHTNING_RESPONSE = {
  scope: "radius",
  lat: 59.33,
  lon: 18.06,
  radius_km: 10,
  period: "month",
  series: [
    {
      period: "7",
      strike_day_probability: 0.4,
      expected_lightning_days: 12.4,
      mean_count: 320,
      year_count: 10,
    },
  ],
  current_month: {
    month: 7,
    observed_lightning_days: 4,
    observed_days: 10,
    climatology_tail_days: 8,
    expected_lightning_days: 12,
    baseline_days: 9,
  },
  meta: { sources: ["smhi-lightning"], attribution: "Source: SMHI", generated_at: "x", year_count: 10 },
};

function renderView(selected: Candidate | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NormalsView selected={selected} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  useChartMock.mockClear();
});

test("shows the Sweden-wide normal when no location is selected", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes("/climatology/lightning") ? LIGHTNING_RESPONSE : CLOUD_RESPONSE;
    return new Response(JSON.stringify(body), { status: 200 });
  });

  renderView(null);

  // No empty prompt — it falls back to the whole-country normal and still draws.
  expect(await screen.findByText(/typical year — all of sweden/i)).toBeInTheDocument();
  expect(await screen.findByText("Source: SMHI")).toBeInTheDocument();
});

test("renders charts and the current-month callouts for a selected location", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes("/climatology/lightning") ? LIGHTNING_RESPONSE : CLOUD_RESPONSE;
    return new Response(JSON.stringify(body), { status: 200 });
  });

  renderView(STOCKHOLM);

  expect(await screen.findByText(/typical year — stockholm/i)).toBeInTheDocument();
  // Both current-month callouts land, phrasing the live month against the normal.
  expect(await screen.findByText(/58% cloud cover/i)).toBeInTheDocument();
  expect(await screen.findByText(/of lightning/i)).toBeInTheDocument();
  expect(await screen.findByText("Source: SMHI")).toBeInTheDocument();

  // The pure option builders' output actually reaches the chart renderer.
  const optionsSeen = useChartMock.mock.calls.map(([option]) => option).filter(Boolean);
  expect(optionsSeen.length).toBeGreaterThan(0);
});

test("queries climatology with the selected coordinates", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    const body = url.includes("/climatology/lightning") ? LIGHTNING_RESPONSE : CLOUD_RESPONSE;
    return new Response(JSON.stringify(body), { status: 200 });
  });

  renderView(STOCKHOLM);
  await screen.findByText("Source: SMHI");

  const cloudUrl = String(
    fetchMock.mock.calls.find(([i]) => String(i).includes("/climatology/cloud"))?.[0],
  );
  expect(cloudUrl).toContain("lat=59.33");
  expect(cloudUrl).toContain("lon=18.06");
  expect(cloudUrl).toContain("period=month");

  const lightningUrl = String(
    fetchMock.mock.calls.find(([i]) => String(i).includes("/climatology/lightning"))?.[0],
  );
  expect(lightningUrl).toContain("radius_km=10");
});
