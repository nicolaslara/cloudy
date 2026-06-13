import { expect, test } from "vitest";
import { periodKeys, periodLabel, tickLabel, zeroFill } from "./series";
import type { LightningPeriod } from "../api/lightning";

const POINT: LightningPeriod = {
  period: "2018-07",
  bucket_start: "2018-07-01T00:00:00Z",
  bucket_end: "2018-08-01T00:00:00Z",
  cg_count: 142,
  all_count: 388,
  lightning_days: 6,
  max_abs_peak_ka: 110.2,
  strongest_event_time: "2018-07-15T12:00:00Z",
};

test("periodKeys enumerates years inclusively", () => {
  expect(periodKeys("year", "2015-01-01", "2018-06-10")).toEqual([
    "2015",
    "2016",
    "2017",
    "2018",
  ]);
});

test("periodKeys enumerates months across a year boundary", () => {
  expect(periodKeys("month", "2017-11-15", "2018-02-01")).toEqual([
    "2017-11",
    "2017-12",
    "2018-01",
    "2018-02",
  ]);
});

test("periodKeys enumerates days, including leap day", () => {
  expect(periodKeys("day", "2020-02-27", "2020-03-01")).toEqual([
    "2020-02-27",
    "2020-02-28",
    "2020-02-29",
    "2020-03-01",
  ]);
});

test("periodKeys enumerates weeks by UTC week start", () => {
  expect(periodKeys("week", "2018-07-01", "2018-07-15")).toEqual([
    "2018-06-25",
    "2018-07-02",
    "2018-07-09",
  ]);
});

test("periodKeys enumerates 6-hour buckets", () => {
  expect(periodKeys("6h", "2018-07-01", "2018-07-01")).toEqual([
    "2018-07-01T00:00:00Z",
    "2018-07-01T06:00:00Z",
    "2018-07-01T12:00:00Z",
    "2018-07-01T18:00:00Z",
  ]);
});

test("zeroFill keeps real points and zeroes the gaps", () => {
  const filled = zeroFill([POINT], "month", "2018-06-01", "2018-08-31");
  expect(filled).toHaveLength(3);
  expect(filled[0]).toEqual({
    period: "2018-06",
    bucket_start: "2018-06-01T00:00:00Z",
    bucket_end: "2018-07-01T00:00:00Z",
    cg_count: 0,
    all_count: 0,
    lightning_days: 0,
    max_abs_peak_ka: 0,
    strongest_event_time: null,
  });
  expect(filled[1]).toEqual(POINT);
  expect(filled[2]?.period).toBe("2018-08");
});

test("zeroFill drops points outside the window", () => {
  const filled = zeroFill([POINT], "month", "2019-01-01", "2019-02-28");
  expect(filled.map((p) => p.period)).toEqual(["2019-01", "2019-02"]);
  expect(filled.every((p) => p.all_count === 0)).toBe(true);
});

test("periodLabel formats per granularity", () => {
  expect(periodLabel("2018", "year")).toBe("2018");
  expect(periodLabel("2018-07", "month")).toBe("Jul 2018");
  expect(periodLabel("2018-07-25", "day")).toBe("25 Jul 2018");
});

test("tickLabel is compact: years always, months show year at January, days at month start", () => {
  expect(tickLabel("2018", "year")).toBe("2018");
  expect(tickLabel("2018-01", "month")).toBe("Jan 2018");
  expect(tickLabel("2018-07", "month")).toBe("Jul");
  expect(tickLabel("2018-07-01", "day")).toBe("1 Jul");
  expect(tickLabel("2018-07-25", "day")).toBe("");
});
