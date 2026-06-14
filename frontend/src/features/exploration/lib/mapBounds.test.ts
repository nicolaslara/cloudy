import { expect, test } from "vitest";
import { boundsForPoints } from "./mapBounds";

test("boundsForPoints returns null for empty input", () => {
  expect(boundsForPoints([])).toBeNull();
});

test("boundsForPoints expands a single point to a minimum span", () => {
  const bounds = boundsForPoints([{ lon: 18.06, lat: 59.33 }], 0.2);
  expect(bounds).not.toBeNull();
  const [[west, south], [east, north]] = bounds!;
  expect(east - west).toBeCloseTo(0.2, 5);
  expect(north - south).toBeCloseTo(0.2, 5);
  expect((west + east) / 2).toBeCloseTo(18.06, 5);
  expect((south + north) / 2).toBeCloseTo(59.33, 5);
});

test("boundsForPoints wraps multiple points", () => {
  const bounds = boundsForPoints([
    { lon: 17.8, lat: 59.2 },
    { lon: 18.4, lat: 59.5 },
  ]);
  const [[west, south], [east, north]] = bounds!;
  expect(west).toBeCloseTo(17.8, 5);
  expect(east).toBeCloseTo(18.4, 5);
  expect(south).toBeCloseTo(59.2, 5);
  expect(north).toBeCloseTo(59.5, 5);
  expect(east - west).toBeGreaterThan(0);
  expect(north - south).toBeGreaterThan(0);
});
