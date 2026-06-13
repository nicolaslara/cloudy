import { expect, test } from "vitest";
import {
  periodEndDay,
  periodStartDay,
  readZoomRange,
  snapRangeToCategories,
} from "./chartZoom";

test("periodStartDay and periodEndDay cover year, month, and day keys", () => {
  expect(periodStartDay("2018")).toBe("2018-01-01");
  expect(periodEndDay("2018")).toBe("2018-12-31");
  expect(periodStartDay("2018-07")).toBe("2018-07-01");
  expect(periodEndDay("2018-07")).toBe("2018-07-31");
  expect(periodStartDay("2018-07-25")).toBe("2018-07-25");
  expect(periodEndDay("2018-07-25")).toBe("2018-07-25");
});

test("readZoomRange reads numeric category indices from the slider", () => {
  const categories = ["2018-07-01", "2018-07-15", "2018-08-01"];
  expect(
    readZoomRange(categories, [{ type: "slider", startValue: 0, endValue: 1 }]),
  ).toEqual({ startDay: "2018-07-01", endDay: "2018-07-15" });
});

test("readZoomRange reads category values from the slider", () => {
  expect(
    readZoomRange(["2018-06", "2018-07", "2018-08"], [
      { type: "slider", startValue: "2018-07", endValue: "2018-08" },
    ]),
  ).toEqual({ startDay: "2018-07-01", endDay: "2018-08-31" });
});

test("readZoomRange reads category values from inside zoom state", () => {
  expect(
    readZoomRange(["2018-06", "2018-07", "2018-08"], [
      { type: "inside", startValue: "2018-07", endValue: "2018-08" },
    ]),
  ).toEqual({ startDay: "2018-07-01", endDay: "2018-08-31" });
});

test("snapRangeToCategories maps a calendar window across granularities", () => {
  const range = { startDay: "2018-07-15", endDay: "2018-08-20" };
  expect(snapRangeToCategories(range, ["2018-06", "2018-07", "2018-08", "2018-09"])).toEqual({
    startValue: "2018-07",
    endValue: "2018-08",
  });
  expect(
    snapRangeToCategories(range, ["2018-07-01", "2018-07-15", "2018-08-01", "2018-08-20"]),
  ).toEqual({
    startValue: "2018-07-15",
    endValue: "2018-08-20",
  });
  expect(snapRangeToCategories(range, ["2017", "2018", "2019"])).toEqual({
    startValue: "2018",
    endValue: "2018",
  });
});
