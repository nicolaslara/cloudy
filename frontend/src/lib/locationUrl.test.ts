import { expect, test, vi } from "vitest";
import {
  candidateFromCoords,
  coordLabel,
  formatCoords,
  isInSweden,
  parseLocationUrl,
  writeLocationToUrl,
} from "./locationUrl";

test("parseLocationUrl reads latlng alone", () => {
  expect(parseLocationUrl("?latlng=59.33,18.06")).toEqual({
    kind: "coords",
    lat: 59.33,
    lon: 18.06,
  });
});

test("parseLocationUrl reads location alone", () => {
  expect(parseLocationUrl("?location=Uppsala")).toEqual({
    kind: "query",
    query: "Uppsala",
  });
});

test("parseLocationUrl ignores both params and logs a warning", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  expect(parseLocationUrl("?latlng=59.33,18.06&location=Stockholm")).toEqual({ kind: "none" });
  expect(warn).toHaveBeenCalledWith(
    "cloudy: URL has both location= and latlng=; ignoring both.",
  );
});

test("parseLocationUrl accepts spaced latlng parts", () => {
  expect(parseLocationUrl("latlng=59.33, 18.06")).toEqual({
    kind: "coords",
    lat: 59.33,
    lon: 18.06,
  });
});

test("parseLocationUrl rejects invalid latlng when it is the only param", () => {
  expect(parseLocationUrl("?latlng=not,coords")).toEqual({ kind: "none" });
});

test("parseLocationUrl rejects coordinates outside Sweden", () => {
  expect(parseLocationUrl("?latlng=40.7,-74.0")).toEqual({ kind: "none" });
});

test("candidateFromCoords uses a coordinate label", () => {
  expect(candidateFromCoords(59.33, 18.06).label).toBe(coordLabel(59.33, 18.06));
  expect(formatCoords(59.33, 18.06)).toBe("59.33,18.06");
});

test("writeLocationToUrl stores either latlng or location, never both", () => {
  window.history.replaceState(null, "", "/");

  writeLocationToUrl({
    label: "Stockholm, Sweden",
    lat: 59.33,
    lon: 18.06,
    provider: "photon",
  });
  expect(window.location.search).toContain("location=Stockholm");
  expect(window.location.search).not.toContain("latlng=");

  writeLocationToUrl(candidateFromCoords(59.33, 18.06));
  expect(new URLSearchParams(window.location.search).get("latlng")).toBe("59.33,18.06");
  expect(window.location.search).not.toContain("location=");
});

test("isInSweden covers Swedish bounds", () => {
  expect(isInSweden(59.33, 18.06)).toBe(true);
  expect(isInSweden(54.9, 18.06)).toBe(false);
});
