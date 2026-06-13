export const STOCKHOLM = {
  label: "Stockholm, Sweden",
  lat: 59.33,
  lon: 18.06,
  provider: "mock",
};

export const GOTHENBURG = {
  label: "Göteborg, Sweden",
  lat: 57.71,
  lon: 11.97,
  provider: "mock",
};

export const HEALTH = { status: "ok", sources: [] };

export const STATION = {
  id: 98230,
  name: "Stockholm-Observatoriekullen A",
  lat: 59.3417,
  lon: 18.0547,
  distance_km: 1.2,
};

export const CLOUD = {
  aggregation: "auto",
  resolved_resolution: "month",
  station: { station_id: 98230, name: "Stockholm-Observatoriekullen A", distance_km: 1.2 },
  series: [
    {
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
    },
  ],
  meta: {
    from: "2015-01-01",
    to: "2026-06-11",
    coverage_fraction: 0.92,
    scope: "station",
    station_count: null,
    sources: ["smhi-metobs"],
    attribution: "Source: SMHI",
    generated_at: "2026-06-11T00:00:00Z",
    total_matched: 12,
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

export const SWEDEN_CLOUD = {
  ...CLOUD,
  station: null,
  meta: {
    ...CLOUD.meta,
    scope: "sweden",
    station_count: 8,
    representation: "cloud_sweden_aggregate_month",
  },
};

const JULY_DAY = (day: number, hour = 14) =>
  Math.floor(Date.parse(`2018-07-${String(day).padStart(2, "0")}T${hour}:00:00Z`) / 1000);

export const LIGHTNING_STROKES = {
  format: "strokes",
  columns: ["lon", "lat", "peak_ka", "cg", "ts"],
  rows: [
    [17.8, 67.2, -42, 1, JULY_DAY(12)],
    [18.1, 67.4, 30, 0, JULY_DAY(12, 16)],
    [15.2, 62.1, -80, 1, JULY_DAY(18)],
    [16.0, 61.5, 12, 0, JULY_DAY(18, 20)],
    [20.4, 63.8, -55, 1, JULY_DAY(25)],
    [21.0, 64.0, 18, 1, JULY_DAY(25, 18)],
  ],
  spatial: { mode: "sweden", bbox: [9, 55, 26, 70] },
  meta: {
    from: "2018-07-01",
    to: "2018-07-31",
    total_matched: 6,
    returned: 6,
    downsampled: false,
    stride: null,
    sample_method: null,
    dropped_count: 0,
    representation: "raw_strokes",
    is_complete: true,
    sources: ["smhi-lightning"],
    attribution: "Source: SMHI",
    generated_at: "2026-06-11T00:00:00Z",
  },
};

/** @deprecated Use LIGHTNING_STROKES */
export const LIGHTNING_EVENTS = LIGHTNING_STROKES;

export const SWEDEN_LIGHTNING = {
  format: "series",
  aggregation: "auto",
  resolved_resolution: "month",
  spatial: { mode: "sweden", bbox: [9, 55, 26, 70] },
  series: [
    {
      period: "2018-07",
      bucket_start: "2018-07-01T00:00:00Z",
      bucket_end: "2018-08-01T00:00:00Z",
      cg_count: 4200,
      all_count: 9800,
      lightning_days: 18,
      max_abs_peak_ka: 145.0,
      strongest_event_time: "2018-07-15T12:00:00Z",
    },
  ],
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

export const LIGHTNING = {
  format: "series",
  aggregation: "auto",
  resolved_resolution: "month",
  spatial: { mode: "radius", lat: STOCKHOLM.lat, lon: STOCKHOLM.lon, radius_km: 10 },
  series: [
    {
      period: "2018-06",
      bucket_start: "2018-06-01T00:00:00Z",
      bucket_end: "2018-07-01T00:00:00Z",
      cg_count: 0,
      all_count: 0,
      lightning_days: 0,
      max_abs_peak_ka: 0,
      strongest_event_time: null,
    },
    {
      period: "2018-07",
      bucket_start: "2018-07-01T00:00:00Z",
      bucket_end: "2018-08-01T00:00:00Z",
      cg_count: 142,
      all_count: 388,
      lightning_days: 6,
      max_abs_peak_ka: 110.2,
      strongest_event_time: "2018-07-15T12:00:00Z",
    },
  ],
  meta: {
    from: "2015-01-01",
    to: "2026-06-11",
    sources: ["smhi-lightning"],
    attribution: "Source: SMHI",
    generated_at: "2026-06-11T00:00:00Z",
    total_matched: 2,
    returned: 2,
    requested_aggregation: "auto",
    resolved_resolution: "month",
    mode: "aggregate",
    representation: "lightning_aggregate_month",
    target_points: 1800,
    point_count: 2,
    is_complete: true,
  },
};
