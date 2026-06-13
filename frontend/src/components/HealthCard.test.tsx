import { afterEach, expect, test, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HealthCard } from "./HealthCard";
import type { Health } from "../api/health";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <HealthCard />
    </QueryClientProvider>,
  );
}

function stubHealth(body: Health) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
}

test("shows ok when backend and database are healthy", async () => {
  stubHealth({ status: "ok", db: "up", version: "0.1.0" });
  renderCard();
  expect(await screen.findByTestId("health-state")).toHaveTextContent("ok");
});

test("shows degraded when the database is unreachable", async () => {
  stubHealth({ status: "degraded", db: "down", version: "0.1.0" });
  renderCard();
  expect(await screen.findByTestId("health-state")).toHaveTextContent("degraded");
});

test("shows unreachable when the request fails", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
  renderCard();
  expect(await screen.findByTestId("health-state")).toHaveTextContent("unreachable");
});
