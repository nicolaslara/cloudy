import { expect, test } from "vitest";
import { countAxisMax, logCountAxisMax } from "./chartAxis";

test("countAxisMax adds headroom above the tallest value", () => {
  expect(countAxisMax({ min: 0, max: 0 })).toBe(1);
  expect(countAxisMax({ min: 0, max: 1 })).toBe(2);
  expect(countAxisMax({ min: 0, max: 10 })).toBe(12);
  expect(countAxisMax({ min: 0, max: 388 })).toBe(435);
});

test("logCountAxisMax adds headroom on the log scale", () => {
  expect(logCountAxisMax({ min: 0, max: 0 })).toBeGreaterThan(0);
  expect(logCountAxisMax({ min: 0, max: 1 })).toBeGreaterThan(1);
});
