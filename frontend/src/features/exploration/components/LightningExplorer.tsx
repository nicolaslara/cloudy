import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import type { Candidate } from "../../../api/geocode";
import {
  HISTORY_START,
  todayIso,
  type Aggregation,
  type RadiusKm,
  type Resolution,
} from "../api/lightning";
import type { ChartScale } from "../lib/chartOption";
import type { LightningPresentation, SliderWindow } from "../lib/lightningExplorer";
import { clampViewportToSweden, type ViewportBbox } from "../lib/mapBounds";
import { periodKeys, zeroFill } from "../lib/series";
import { useChartState } from "../lib/useChartState";
import { useLightningExploreData } from "../lib/useLightningExploreData";
import { useElementWidth } from "../../../lib/useElementWidth";
import { Segmented } from "../../../components/Segmented";
import { CloudChartPane } from "./CloudChartPane";
import { LightningChartPane } from "./LightningChartPane";
import { UnifiedChartPane } from "./UnifiedChartPane";
import { LightningMapPane } from "./LightningMapPane";
import { TimeRangePicker } from "./TimeRangePicker";

const AGGREGATIONS: Aggregation[] = ["auto", "week", "month", "year"];
const RADII: RadiusKm[] = [10, 25];
const SLIDER_WINDOW_PRESETS: SliderWindow[] = ["day", "week", "month", "year"];
const VARIABLES = ["unified", "lightning", "cloud"] as const;
type ExploreVariable = (typeof VARIABLES)[number];
const SCALES: ChartScale[] = ["linear", "log"];

const VARIABLE_LABEL: Record<ExploreVariable, string> = {
  unified: "Unified",
  lightning: "Lightning",
  cloud: "Cloud",
};

const AGGREGATION_LABEL: Record<Aggregation, string> = {
  auto: "Auto",
  week: "Weekly",
  month: "Monthly",
  year: "Yearly",
};

const RESOLUTION_LABEL: Record<Resolution, string> = {
  raw: "raw",
  hour: "hourly",
  "6h": "6-hour",
  day: "daily",
  week: "weekly",
  month: "monthly",
  year: "yearly",
};

const SLIDER_WINDOW_LABEL: Record<SliderWindow, string> = {
  day: "1 day",
  week: "1 week",
  month: "1 month",
  year: "1 year",
  custom: "Custom",
};

const SCALE_LABEL: Record<ChartScale, string> = {
  linear: "Linear",
  log: "Log",
};

/**
 * Thin orchestrator. The two hard parts — the chart-state cascade
 * (aggregation/zoom/range move as one) and the four coupled data queries — live
 * in useChartState and useLightningExploreData respectively. What's left here is
 * the genuinely local stuff: which variable/radius/scale the user picked, and how
 * to lay out the controls and panes for the current variable×presentation cell.
 */
export function LightningExplorer({
  selected,
  presentation,
}: {
  selected: Candidate | null;
  presentation: LightningPresentation;
}) {
  const fetchFrom = HISTORY_START;
  const fetchTo = todayIso();
  const [sectionRef, sectionWidth] = useElementWidth<HTMLElement>();
  const [variable, setVariable] = useState<ExploreVariable>("unified");
  const [radiusKm, setRadiusKm] = useState<RadiusKm>(10);
  const [scale, setScale] = useState<ChartScale>("linear");
  // With no location selected, the map viewport scopes the strokes query
  // (clamped to the API's Sweden bounds; null = Sweden-wide default).
  const [viewportBbox, setViewportBbox] = useState<ViewportBbox | null>(null);

  const {
    aggregation,
    sliderWindow,
    visibleZoom,
    calendarRange,
    sliderVisibleZoom,
    timeSliderResolution,
    setAggregation,
    setSliderWindow,
    handleChartVisibleZoom,
    handleSliderVisibleZoom,
    resnap,
  } = useChartState({ fetchFrom, fetchTo });

  // The series query trails the slider by a frame so dragging stays smooth; the
  // visible window still snaps instantly off the non-deferred state above.
  const chartCalendarRange = useDeferredValue(calendarRange);
  const chartWidth = sectionWidth === undefined ? undefined : Math.max(300, sectionWidth - 32);

  const exploreData = useLightningExploreData({
    selected,
    presentation,
    variable,
    aggregation,
    radiusKm,
    calendarRange: chartCalendarRange,
    visibleZoom,
    viewportBbox,
    chartWidth,
    fetchFrom,
    fetchTo,
  });
  const {
    showLightning,
    showCloud,
    chartQueryFrom,
    chartQueryTo,
    chartResolution,
    cloudRange,
    cloudResolution,
  } = exploreData;
  // Alias the query results back to the names the markup below already uses, so
  // the rendering stayed untouched when the fetching moved into the data hook.
  const { data, isPending, error } = exploreData.lightning;
  const cloudQuery = exploreData.cloud;
  const monthSliderSeries = exploreData.monthSlider.data;
  const monthSliderPending = exploreData.monthSlider.isPending;
  const strokesQuery = exploreData.strokes;

  const sliderPeriods = useMemo(
    () => periodKeys(timeSliderResolution, fetchFrom, fetchTo),
    [timeSliderResolution, fetchFrom, fetchTo],
  );
  const sliderFilled = useMemo(
    () =>
      monthSliderSeries && monthSliderSeries.series.length > 0
        ? zeroFill(monthSliderSeries.series, timeSliderResolution, fetchFrom, fetchTo)
        : [],
    [monthSliderSeries, timeSliderResolution, fetchFrom, fetchTo],
  );
  const sliderCounts = useMemo(
    () => sliderFilled.map((point) => point.all_count),
    [sliderFilled],
  );
  const timeSliderStructureKey = `${fetchFrom}:${fetchTo}:${timeSliderResolution}`;
  const chartStructureKey = `${chartQueryFrom}:${chartQueryTo}:${chartResolution}`;
  const cloudStructureKey = `cloud:${cloudRange.from}:${cloudRange.to}:${cloudResolution}`;
  const sliderWindowOptions: SliderWindow[] =
    sliderWindow === "custom" ? [...SLIDER_WINDOW_PRESETS, "custom"] : SLIDER_WINDOW_PRESETS;
  const showTimeRangePicker =
    (presentation === "map" || showLightning || (variable === "cloud" && selected !== null)) &&
    !monthSliderPending &&
    sliderFilled.length > 0;

  const scopeLabel = selected
    ? `${radiusKm} km around ${selected.label}`
    : "all of Sweden";

  const cloudStationLabel = cloudQuery.data?.station
    ? `${cloudQuery.data.station.name}, ${cloudQuery.data.station.distance_km} km away`
    : cloudQuery.data?.meta.station_count
      ? `Sweden-wide station aggregate (${cloudQuery.data.meta.station_count} stations)`
      : "Sweden-wide station aggregate";

  const isEmpty = data !== undefined && data.series.length === 0;
  const cloudEmpty = cloudQuery.data !== undefined && cloudQuery.data.series.length === 0;
  const attribution =
    presentation === "chart" && variable === "cloud"
      ? cloudQuery.data?.meta.attribution
      : presentation === "chart" && variable === "unified"
        ? data?.meta.attribution ?? cloudQuery.data?.meta.attribution
        : presentation === "chart"
          ? data?.meta.attribution
          : strokesQuery.data?.meta.attribution;

  // When the live resolution changes (auto resolved differently) or we return
  // from the map to the chart, the calendar window holds but the visible zoom has
  // to re-grid onto the new bucket size. The reducer owns that re-snap; these
  // effects just watch for the triggers the reducer can't see.
  const prevPresentation = useRef(presentation);
  const prevResolution = useRef(chartResolution);
  useEffect(() => {
    if (prevPresentation.current === "map" && presentation === "chart") {
      resnap(chartResolution);
    }
    prevPresentation.current = presentation;
  }, [presentation, chartResolution, resnap]);

  useEffect(() => {
    if (prevResolution.current !== chartResolution && presentation === "chart") {
      resnap(chartResolution);
    }
    prevResolution.current = chartResolution;
  }, [chartResolution, presentation, resnap]);

  return (
    <section
      ref={sectionRef}
      className={`lightning-explorer ${presentation === "map" ? "lightning-explorer-map" : ""}`}
    >
      <div className="chart-controls">
        <Segmented
          label="Visible range"
          options={sliderWindowOptions}
          value={sliderWindow}
          onChange={(next) => setSliderWindow(next, chartResolution)}
          format={(option) => SLIDER_WINDOW_LABEL[option]}
        />
        {presentation === "chart" && (
          <Segmented
            label="Chart"
            options={[...VARIABLES]}
            value={variable}
            onChange={setVariable}
            format={(option) => VARIABLE_LABEL[option]}
          />
        )}
        {presentation === "chart" && (
          <Segmented
            label="Group by"
            options={AGGREGATIONS}
            value={aggregation}
            onChange={setAggregation}
            format={(option) => AGGREGATION_LABEL[option]}
          />
        )}
        {presentation === "chart" && showLightning && (
          <Segmented
            label="Lightning radius"
            options={RADII}
            value={radiusKm}
            onChange={setRadiusKm}
            format={(option) => `${option} km`}
            disabled={!selected}
          />
        )}
        {presentation === "chart" && showLightning && (
          <Segmented
            label="Strike scale"
            options={SCALES}
            value={scale}
            onChange={setScale}
            format={(option) => SCALE_LABEL[option]}
          />
        )}
        {presentation === "map" && (
          <Segmented
            label="Search radius"
            options={RADII}
            value={radiusKm}
            onChange={setRadiusKm}
            format={(option) => `${option} km`}
            disabled={!selected}
          />
        )}
      </div>
      {presentation === "chart" && showLightning && !selected && (
        <p className="chart-note">Showing Sweden-wide totals. Search an address to filter by radius.</p>
      )}
      {presentation === "chart" && showLightning && aggregation === "auto" && data && (
        <p className="chart-note">
          Auto resolved to {RESOLUTION_LABEL[chartResolution]} buckets.
        </p>
      )}
      {presentation === "chart" && chartResolution === "day" && showLightning && !isEmpty && !isPending && !error && (
        <p className="chart-note">
          Daily buckets — change Visible range to inspect a shorter or longer window.
        </p>
      )}
      {presentation === "map" && (
        <p className="chart-note">
          Each dot is one strike (lat/lon from SMHI). The slider only picks which days to load — nothing is summed per day.
        </p>
      )}

      {presentation === "chart" && variable === "unified" ? (
        <UnifiedChartPane
          lightningData={data}
          cloudData={cloudQuery.data}
          resolution={chartResolution}
          scale={scale}
          fetchFrom={chartQueryFrom}
          fetchTo={chartQueryTo}
          cloudQueryFrom={cloudRange.from}
          cloudQueryTo={cloudRange.to}
          visibleZoom={visibleZoom}
          structureKey={`unified:${chartStructureKey}`}
          scopeLabel={scopeLabel}
          stationLabel={cloudStationLabel}
          hasCloud={showCloud}
          lightningPending={isPending}
          cloudPending={cloudQuery.isPending}
          cloudFetching={cloudQuery.isFetching}
          lightningError={error}
          cloudError={cloudQuery.error}
          onVisibleZoom={(next) => handleChartVisibleZoom(next, chartResolution)}
        />
      ) : presentation === "chart" && variable === "lightning" ? (
        <LightningChartPane
          data={data}
          resolution={chartResolution}
          scale={scale}
          fetchFrom={chartQueryFrom}
          fetchTo={chartQueryTo}
          visibleZoom={visibleZoom}
          structureKey={chartStructureKey}
          scopeLabel={scopeLabel}
          isPending={isPending}
          error={error}
          onVisibleZoom={(next) => handleChartVisibleZoom(next, chartResolution)}
        />
      ) : presentation === "chart" ? (
        <CloudChartPane
          data={cloudQuery.data}
          resolution={cloudResolution}
          queryFrom={cloudRange.from}
          queryTo={cloudRange.to}
          visibleZoom={visibleZoom}
          structureKey={cloudStructureKey}
          stationLabel={cloudStationLabel}
          isPending={cloudQuery.isPending}
          isFetching={cloudQuery.isFetching}
          error={cloudQuery.error}
          onVisibleZoom={(next) => handleChartVisibleZoom(next, chartResolution)}
        />
      ) : (
        <LightningMapPane
          selected={selected}
          radiusKm={radiusKm}
          visibleZoom={visibleZoom}
          strokes={strokesQuery.data}
          strokesFetching={strokesQuery.isFetching}
          strokesError={strokesQuery.error}
          onUserViewport={(viewport) => setViewportBbox(clampViewportToSweden(viewport))}
        />
      )}

      {showTimeRangePicker && (
        <TimeRangePicker
          periods={sliderPeriods}
          counts={sliderCounts}
          resolution={timeSliderResolution}
          visibleZoom={sliderVisibleZoom}
          label={`${calendarRange.startDay} — ${calendarRange.endDay}`}
          structureKey={timeSliderStructureKey}
          onVisibleZoom={(next) => handleSliderVisibleZoom(next, chartResolution, presentation)}
        />
      )}

      {attribution &&
        (presentation === "map" ||
          (showLightning && !isEmpty) ||
          (showCloud && !cloudEmpty)) && (
        <p className="chart-attribution">{attribution}</p>
      )}
    </section>
  );
}
