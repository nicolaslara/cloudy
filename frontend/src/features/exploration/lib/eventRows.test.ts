import { expect, test } from "vitest";
import {
  dailyCounts,
  filterByDayRange,
  listDays,
  parseEventRows,
  strokeColor,
  strokeTooltipHtml,
} from "./eventRows";

test("parseEventRows maps compact arrays to points", () => {
  const ts = Math.floor(Date.parse("2018-07-25T12:00:00Z") / 1000);
  const points = parseEventRows([[18.1, 59.3, -45, 1, ts]]);
  expect(points[0]).toMatchObject({ lon: 18.1, lat: 59.3, peakKa: -45, cg: true, day: "2018-07-25" });
});

test("dailyCounts aggregates by day", () => {
  const dayA = Math.floor(Date.parse("2018-07-24T12:00:00Z") / 1000);
  const dayB = Math.floor(Date.parse("2018-07-25T12:00:00Z") / 1000);
  const points = parseEventRows([
    [18, 59, 10, 1, dayA],
    [18.1, 59.1, 20, 0, dayA],
    [17.9, 59.2, 5, 1, dayB],
  ]);
  expect(dailyCounts(points)).toEqual([
    { day: "2018-07-24", count: 2 },
    { day: "2018-07-25", count: 1 },
  ]);
});

test("filterByDayRange keeps inclusive calendar bounds", () => {
  const dayA = Math.floor(Date.parse("2018-07-24T12:00:00Z") / 1000);
  const dayB = Math.floor(Date.parse("2018-07-25T12:00:00Z") / 1000);
  const dayC = Math.floor(Date.parse("2018-07-26T12:00:00Z") / 1000);
  const points = parseEventRows([
    [18, 59, 10, 1, dayA],
    [18.1, 59.1, 20, 0, dayB],
    [17.9, 59.2, 5, 1, dayC],
  ]);
  expect(filterByDayRange(points, "2018-07-24", "2018-07-25")).toHaveLength(2);
});

test("strokeColor distinguishes CG from IC", () => {
  const cg = parseEventRows([[18, 59, 10, 1, 0]])[0]!;
  const ic = parseEventRows([[18, 59, 10, 0, 0]])[0]!;
  expect(strokeColor(cg)[0]).toBeGreaterThan(strokeColor(ic)[0]);
});

test("listDays is inclusive", () => {
  expect(listDays("2018-07-01", "2018-07-03")).toEqual(["2018-07-01", "2018-07-02", "2018-07-03"]);
});

test("strokeTooltipHtml formats kind, UTC time, and signed peak current", () => {
  const point = {
    lon: 18.06,
    lat: 59.33,
    peakKa: -110.25,
    cg: true,
    ts: Date.UTC(2018, 6, 25, 14, 30) / 1000,
    day: "2018-07-25",
  };
  const html = strokeTooltipHtml(point);
  expect(html).toContain("Cloud-to-ground");
  expect(html).toContain("2018-07-25 14:30 UTC");
  expect(html).toContain("−110.3 kA");
});
