import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { DampedPersistenceView } from "./DampedPersistenceView";
import { skillHistogramOption } from "./skillHistogramOption";

describe("skillHistogramOption", () => {
  test("bins per-station skills into counted bars", () => {
    const option = skillHistogramOption([-1, 0.5, 1.2, 1.8, 3.1, 22.8]);
    const series = option.series as { type: string; data: { value: number }[] }[];
    expect(series[0]?.type).toBe("bar");
    // The bar counts sum back to the number of stations supplied.
    const total = series[0]?.data.reduce((a, d) => a + d.value, 0);
    expect(total).toBe(6);
  });

  test("handles an empty benchmark without throwing", () => {
    const option = skillHistogramOption([]);
    expect((option.series as unknown[]).length).toBe(0);
  });
});

const ARTIFACT = {
  generated_at: "x",
  n_stations: 109,
  models: {
    damped: {
      median_skill_pct: 2.1,
      fraction_beating: 0.98,
      lead2_median_skill_pct: 0.3,
      lead1_skills: [-1.3, 0.3, 1.1, 2.1, 3.0, 10.9, 22.8],
    },
  },
};

const useChartMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/useChart", () => ({
  useChart: (option: unknown) => {
    useChartMock(option);
    return { containerRef: { current: null }, chartRef: { current: null } };
  },
}));

afterEach(() => vi.restoreAllMocks());

test("Damped-persistence tab explains the model and headlines the backtest result", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () => new Response(JSON.stringify(ARTIFACT), { status: 200 }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DampedPersistenceView selected={null} />
    </QueryClientProvider>,
  );

  expect(
    await screen.findByRole("heading", { name: "Damped persistence", level: 2 }),
  ).toBeInTheDocument();
  expect(screen.getByText(/damped anomaly persistence/i)).toBeInTheDocument();
  // The honest headline: beats the normal at 98% of stations (prose + leaderboard).
  expect((await screen.findAllByText(/98%/)).length).toBeGreaterThan(0);
  // The leaderboard lists the damped-persistence model.
  expect((await screen.findAllByText("Damped persistence")).length).toBeGreaterThan(0);
});
