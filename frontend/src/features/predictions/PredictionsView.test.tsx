import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { Candidate } from "../../api/geocode";
import { PredictionsView } from "./PredictionsView";

const STOCKHOLM: Candidate = { label: "Stockholm", lat: 59.33, lon: 18.06, provider: "mock" };

// A located outlook: the latest week ran well above normal, so the next two weeks
// are expected above normal too, with real backtested skill.
const OUTLOOK = {
  scope: "station",
  radius_km: 50,
  recent_anomaly_pct: 19.1,
  recent_cloud_pct: 70.0,
  weeks_observed: 480,
  leads: [
    {
      lead_weeks: 1,
      alpha: 0.68,
      expected_anomaly_pct: 13.0,
      expected_cloud_pct: 64.0,
      target_week: 30,
      skill: 0.29,
      n_origins: 477,
    },
    {
      lead_weeks: 2,
      alpha: 0.63,
      expected_anomaly_pct: 12.0,
      expected_cloud_pct: 63.0,
      target_week: 31,
      skill: 0.21,
      n_origins: 476,
    },
  ],
  meta: { sources: ["smhi-metobs"], attribution: "Source: SMHI", generated_at: "x" },
};

// The point-precise normals behind the progression, keyed by model: nearest station,
// kNN average — increasingly cloudy at the lead-1 target week (30), so the table reads
// as a sharpening ladder. Damped adds the +13.0 pp anomaly.
const SPATIAL_NORMAL: Record<string, number> = { nearest: 48, knn: 50 };
function spatialResponse(model: string) {
  return {
    lat: 59.33,
    lon: 18.06,
    model,
    nearest_station: { station_id: 1, name: "Test A", distance_km: 12.0 },
    n_neighbours: model === "nearest" ? 1 : 5,
    series: [{ week: 30, estimated_cloud_pct: SPATIAL_NORMAL[model] ?? null }],
    meta: { sources: ["smhi-metobs"], attribution: "Source: SMHI", generated_at: "x" },
  };
}

// A near-normal outlook: no real gap to carry forward.
const FLAT_OUTLOOK = {
  ...OUTLOOK,
  scope: "sweden",
  recent_anomaly_pct: 0.4,
  recent_cloud_pct: 55.0,
  leads: [
    {
      lead_weeks: 1,
      alpha: 0.29,
      expected_anomaly_pct: 0.1,
      expected_cloud_pct: 55.0,
      skill: 0.05,
      n_origins: 493,
    },
    {
      lead_weeks: 2,
      alpha: 0.12,
      expected_anomaly_pct: 0.0,
      expected_cloud_pct: 55.0,
      skill: 0.01,
      n_origins: 492,
    },
  ],
};

// A located lightning outlook: last summer's data ran above normal; the series is
// `as_of` that week (lightning trails the calendar out of season).
const LIGHTNING = {
  scope: "radius",
  radius_km: 25,
  recent_anomaly_days: 1.8,
  recent_lightning_days: 3.0,
  weeks_observed: 200,
  as_of_week: "2025-08-04",
  leads: [
    {
      lead_weeks: 1,
      alpha: 0.4,
      expected_anomaly_days: 0.7,
      expected_lightning_days: 1.9,
      skill: 0.06,
      n_origins: 96,
    },
    {
      lead_weeks: 2,
      alpha: 0.2,
      expected_anomaly_days: 0.4,
      expected_lightning_days: 1.6,
      skill: 0.02,
      n_origins: 95,
    },
  ],
  meta: { sources: ["smhi-lightning"], attribution: "Source: SMHI", generated_at: "x" },
};

// Route by endpoint so the cloud, lightning, and spatial-baseline calls each get
// their own shape. The spatial responder defaults to an empty series so panels that
// don't care about the progression (Sweden-wide, lightning-only tests) still degrade
// gracefully rather than crash.
function mockFetch(
  cloud: unknown,
  lightning: unknown = { recent_anomaly_days: null },
  spatial: (model: string) => unknown = () => ({ series: [] }),
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    let body: unknown;
    if (url.includes("/predictions/spatial")) {
      const model = new URL(url, "http://localhost").searchParams.get("model") ?? "";
      body = spatial(model);
    } else if (url.includes("lightning-outlook")) {
      body = lightning;
    } else {
      body = cloud;
    }
    return new Response(JSON.stringify(body), { status: 200 });
  });
}

function renderView(selected: Candidate | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PredictionsView selected={selected} />
    </QueryClientProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

test("shows the located outlook as a progression: normal two ways, then damped", async () => {
  mockFetch(OUTLOOK, undefined, spatialResponse);
  renderView(STOCKHOLM);

  expect(await screen.findByText(/near-term outlook — stockholm/i)).toBeInTheDocument();
  // The headline absolute prediction (the deployed, backtested model).
  expect(await screen.findByText("~64%")).toBeInTheDocument();

  // The two baseline rows, increasingly precise spatial estimates of the normal.
  expect(await screen.findByText("Nearest station")).toBeInTheDocument();
  expect(await screen.findByText("Average of nearby (kNN)")).toBeInTheDocument();

  // Seasonal-normal column for nearest (48) and kNN (50), and the damped column that
  // adds the +13.0 pp anomaly (48 -> 61, 50 -> 63). The kNN damped value (63) also
  // matches the headline week-after figure, so it can appear more than once.
  expect(await screen.findByText("~48%")).toBeInTheDocument();
  expect(await screen.findByText("~61%")).toBeInTheDocument();
  expect(await screen.findByText("~50%")).toBeInTheDocument();
  expect((await screen.findAllByText("~63%")).length).toBeGreaterThan(0);

  // The narrative: recent gap and the damped step's skill.
  expect(await screen.findByText(/estimated at your point two ways/i)).toBeInTheDocument();
  expect(await screen.findByText(/\+19\.1 pp/)).toBeInTheDocument();
  expect(await screen.findByText(/\+29% at 1 week/)).toBeInTheDocument();
  expect(await screen.findByText("Source: SMHI")).toBeInTheDocument();
});

test("falls back to the Sweden-wide outlook with no location, and says 'about normal'", async () => {
  mockFetch(FLAT_OUTLOOK);
  renderView(null);

  expect(await screen.findByText(/near-term outlook — all of sweden/i)).toBeInTheDocument();
  expect(await screen.findByText(/tracks the seasonal normal/i)).toBeInTheDocument();
});

test("states the lightning outlook in lightning-days, as-of its week, with a caveat", async () => {
  mockFetch(OUTLOOK, LIGHTNING);
  renderView(STOCKHOLM);

  // The recent gap is in lightning-days and names the week it's as-of.
  expect(await screen.findByText(/\+1\.8 days/)).toBeInTheDocument();
  expect(await screen.findByText(/week of 2025-08-04/)).toBeInTheDocument();
  // The absolute expected lightning-days lead and the sparsity caveat are both stated.
  expect(await screen.findByText(/~1\.9/)).toBeInTheDocument();
  expect(await screen.findByText(/sparse and bursty/i)).toBeInTheDocument();
});

test("queries both outlooks with the selected coordinates", async () => {
  const fetchMock = mockFetch(OUTLOOK, LIGHTNING);
  renderView(STOCKHOLM);
  await screen.findByText(/\+1\.8 days/);

  const lightningUrl = String(
    fetchMock.mock.calls.find(([i]) => String(i).includes("/predictions/lightning-outlook"))?.[0],
  );
  expect(lightningUrl).toContain("lat=59.33");
  expect(lightningUrl).toContain("radius_km=25");
});

test("queries the outlook with the selected coordinates", async () => {
  const fetchMock = mockFetch(OUTLOOK);
  renderView(STOCKHOLM);
  await screen.findByText("Source: SMHI");

  const url = String(fetchMock.mock.calls.find(([i]) => String(i).includes("/predictions/outlook"))?.[0]);
  expect(url).toContain("lat=59.33");
  expect(url).toContain("lon=18.06");
  expect(url).toContain("radius_km=50");
});
