import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useSelectedLocation } from "./useSelectedLocation";

const STOCKHOLM = {
  label: "Stockholm, Sweden",
  lat: 59.33,
  lon: 18.06,
  provider: "mock",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

test("loads coordinates from ?latlng= on mount", async () => {
  window.history.replaceState(null, "", "/?latlng=59.33,18.06");

  const { result } = renderHook(() => useSelectedLocation(), { wrapper });

  await waitFor(() => {
    expect(result.current.selected?.lat).toBe(59.33);
    expect(result.current.selected?.lon).toBe(18.06);
  });
});

test("resolves ?location= via geocode and keeps only location in the URL", async () => {
  window.history.replaceState(null, "", "/?location=Stockholm");
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/v1/geocode")) {
      return new Response(JSON.stringify([STOCKHOLM]), { status: 200 });
    }
    throw new Error(`unexpected fetch ${String(input)}`);
  });

  const { result } = renderHook(() => useSelectedLocation(), { wrapper });

  await waitFor(() => {
    expect(result.current.selected?.label).toBe(STOCKHOLM.label);
  });
  expect(window.location.search).toContain("location=Stockholm");
  expect(window.location.search).not.toContain("latlng=");
});

test("setSelected from search writes location only", async () => {
  const { result } = renderHook(() => useSelectedLocation(), { wrapper });

  result.current.setSelected({ ...STOCKHOLM, provider: "photon" });

  await waitFor(() => {
    expect(window.location.search).toContain("location=Stockholm");
    expect(window.location.search).not.toContain("latlng=");
  });
});
