import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SearchBox } from "./SearchBox";

const CANDIDATE = {
  label: "Drottninggatan, 111 52, Stockholm",
  lat: 59.33,
  lon: 18.06,
  provider: "photon",
};

function renderBox(onSelect = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SearchBox onSelect={onSelect} />
    </QueryClientProvider>,
  );
  return onSelect;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function mockGeocode() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.startsWith("/api/v1/geocode")) {
      return new Response(JSON.stringify([CANDIDATE]), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

test("typing shows debounced suggestions; clicking one calls onSelect", async () => {
  mockGeocode();
  const onSelect = renderBox();

  await userEvent.type(screen.getByLabelText("Address search"), "Drottninggatan");
  const suggestion = await screen.findByRole("button", { name: /Drottninggatan/ });
  await userEvent.click(suggestion);

  await waitFor(() => {
    expect(onSelect).toHaveBeenCalledWith(CANDIDATE);
  });
  // Selecting clears the input — no saved state anywhere.
  expect(screen.getByLabelText("Address search")).toHaveValue("");
});

test("arrow keys + Enter select a suggestion", async () => {
  mockGeocode();
  const onSelect = renderBox();

  const box = screen.getByLabelText("Address search");
  await userEvent.type(box, "Drottninggatan");
  await screen.findByRole("option");
  await userEvent.keyboard("{ArrowDown}{Enter}");

  await waitFor(() => {
    expect(onSelect).toHaveBeenCalledWith(CANDIDATE);
  });
});

test("shows a notice when the geocoder is unavailable", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("rate limited", { status: 429 }));

  renderBox();
  await userEvent.type(screen.getByLabelText("Address search"), "Drottninggatan");

  expect(await screen.findByText(/search is unavailable/i)).toBeInTheDocument();
});
