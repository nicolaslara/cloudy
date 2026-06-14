import { expect, test } from "vitest";
import {
  addCalendarDays,
  calendarRangeForWindow,
  defaultVisibleZoom,
  filterSeriesByZoom,
  translateVisibleZoom,
  visibleZoomForWindow,
  visibleZoomToDayRange,
} from "./lightningExplorer";
import type { LightningPeriod } from "../api/lightning";

const FROM = "2015-01-01";
const TO = "2020-12-31";

test("defaultVisibleZoom opens on a one-year window ending today", () => {
  const zoom = defaultVisibleZoom("day", FROM, TO, "year");
  expect(zoom).toEqual({
    startPeriod: addCalendarDays(TO, -364),
    endPeriod: TO,
  });
});

test("visibleZoomForWindow maps calendar spans onto period keys", () => {
  expect(visibleZoomForWindow("day", "2018-07-15", "day", FROM, TO)).toEqual({
    startPeriod: "2018-07-15",
    endPeriod: "2018-07-15",
  });
  expect(visibleZoomForWindow("week", "2018-07-15", "month", FROM, TO)).toEqual({
    startPeriod: "2018-07",
    endPeriod: "2018-07",
  });
  expect(visibleZoomForWindow("year", TO, "month", FROM, TO)).toEqual({
    startPeriod: "2020-01",
    endPeriod: "2020-12",
  });
});

test("calendarRangeForWindow is independent of chart resolution", () => {
  expect(calendarRangeForWindow("week", "2026-06-30", FROM, "2026-06-12")).toEqual({
    startDay: "2026-06-06",
    endDay: "2026-06-12",
  });
});

test("visibleZoomToDayRange maps period keys to calendar days", () => {
  expect(
    visibleZoomToDayRange({ startPeriod: "2018-07", endPeriod: "2018-08" }),
  ).toEqual({ from: "2018-07-01", to: "2018-08-31" });
});

test("translateVisibleZoom preserves the calendar window across granularities", () => {
  const dayZoom = { startPeriod: "2018-07-15", endPeriod: "2018-08-20" };
  expect(translateVisibleZoom(dayZoom, "month", FROM, TO)).toEqual({
    startPeriod: "2018-07",
    endPeriod: "2018-08",
  });
});

test("filterSeriesByZoom keeps only periods inside the window", () => {
  const series: LightningPeriod[] = [
    lightningPoint("2018-06", 0, 0, 0, 0),
    lightningPoint("2018-07", 1, 2, 1, 10),
    lightningPoint("2018-08", 0, 1, 1, 5),
  ];
  expect(
    filterSeriesByZoom(series, { startPeriod: "2018-07", endPeriod: "2018-07" }),
  ).toEqual([series[1]]);
});

function lightningPoint(
  period: string,
  cgCount: number,
  allCount: number,
  lightningDays: number,
  maxAbsPeakKa: number,
): LightningPeriod {
  return {
    period,
    bucket_start: `${period}-01T00:00:00Z`,
    bucket_end: `${period}-02T00:00:00Z`,
    cg_count: cgCount,
    all_count: allCount,
    lightning_days: lightningDays,
    max_abs_peak_ka: maxAbsPeakKa,
    strongest_event_time: null,
  };
}
