import { useCallback, useMemo, useReducer } from "react";
import { snapRangeToCategories, type ZoomRange } from "./chartZoom";
import { periodKeys } from "./series";
import {
  calendarRangeForWindow,
  defaultVisibleZoom,
  fallbackResolution,
  isSliderWindowPreset,
  visibleZoomToCalendarRange,
  type LightningPresentation,
  type SliderWindow,
  type VisibleZoom,
} from "./lightningExplorer";
import type { Aggregation, Resolution } from "../api/lightning";

/**
 * `aggregation`, `visibleZoom`, and `calendarRange` move as a single triad, not
 * three independent knobs. The calendar range is the source of truth (which days
 * are on screen); the visible zoom is that same window *snapped to the chart's
 * bucket grid*, and the aggregation decides how fine that grid is. So changing
 * any one can force the others to re-derive — pick weekly buckets and the zoom
 * must re-snap; drag the slider and both the range and the window move together.
 * Keeping them in one reducer is what makes that cascade legible instead of a
 * web of cross-firing setState calls. `sliderWindow` rides along because picking
 * a preset writes the range, and any other edit demotes the label to "custom".
 *
 * The live chart resolution isn't reducer state — it depends on query data the
 * component fetches — so it rides into each action (and the resnap call) as an
 * argument rather than being closed over.
 */
type ChartState = {
  aggregation: Aggregation;
  sliderWindow: SliderWindow;
  visibleZoom: VisibleZoom;
  calendarRange: ZoomRange;
};

type Action =
  | { type: "setAggregation"; next: Aggregation }
  | { type: "setSliderWindow"; next: SliderWindow; resolution: Resolution }
  | { type: "chartVisibleZoom"; next: VisibleZoom; resolution: Resolution }
  | {
      type: "sliderVisibleZoom";
      next: VisibleZoom;
      sliderResolution: Resolution;
      chartResolution: Resolution;
      presentation: LightningPresentation;
    }
  | { type: "resnap"; resolution: Resolution };

/**
 * Snap a calendar range onto a resolution's period grid. This is the bridge
 * between "which days" (the range) and "which buckets" (the visible zoom).
 */
function zoomFor(
  range: ZoomRange,
  resolution: Resolution,
  fetchFrom: string,
  fetchTo: string,
): VisibleZoom {
  const categories = periodKeys(resolution, fetchFrom, fetchTo);
  if (categories.length === 0) {
    return { startPeriod: range.startDay, endPeriod: range.endDay };
  }
  const { startValue, endValue } = snapRangeToCategories(range, categories, resolution);
  return { startPeriod: startValue, endPeriod: endValue };
}

function reducer(
  state: ChartState,
  action: Action & { fetchFrom: string; fetchTo: string },
): ChartState {
  const { fetchFrom, fetchTo } = action;
  switch (action.type) {
    case "setAggregation":
      // The range stays put; only the bucket grid (and thus the snap) changes.
      // Note the original used the optimistic `fallbackResolution(next)` here, not
      // the resolved resolution — the API hasn't answered the new aggregation yet.
      return {
        ...state,
        aggregation: action.next,
        visibleZoom: zoomFor(
          state.calendarRange,
          fallbackResolution(action.next),
          fetchFrom,
          fetchTo,
        ),
      };
    case "setSliderWindow": {
      if (!isSliderWindowPreset(action.next)) {
        return { ...state, sliderWindow: action.next };
      }
      const range = calendarRangeForWindow(action.next, state.calendarRange.endDay, fetchFrom, fetchTo);
      return {
        ...state,
        sliderWindow: action.next,
        calendarRange: range,
        visibleZoom: zoomFor(range, action.resolution, fetchFrom, fetchTo),
      };
    }
    case "chartVisibleZoom": {
      // A no-op nudge (same window) just records the zoom without disturbing the
      // range/label — this is the chart echoing its own position back.
      if (
        action.next.startPeriod === state.visibleZoom.startPeriod &&
        action.next.endPeriod === state.visibleZoom.endPeriod
      ) {
        return { ...state, visibleZoom: action.next };
      }
      return {
        ...state,
        sliderWindow: "custom",
        calendarRange: visibleZoomToCalendarRange(action.next, action.resolution),
        visibleZoom: action.next,
      };
    }
    case "sliderVisibleZoom": {
      // Ignore the slider echoing its own current position (it speaks month
      // buckets; compare against where it currently sits).
      const currentSliderZoom = zoomFor(state.calendarRange, action.sliderResolution, fetchFrom, fetchTo);
      if (
        action.next.startPeriod === currentSliderZoom.startPeriod &&
        action.next.endPeriod === currentSliderZoom.endPeriod
      ) {
        return state;
      }
      const range = visibleZoomToCalendarRange(action.next, action.sliderResolution);
      const targetResolution =
        action.presentation === "map" ? action.sliderResolution : action.chartResolution;
      return {
        ...state,
        sliderWindow: "custom",
        calendarRange: range,
        visibleZoom: zoomFor(range, targetResolution, fetchFrom, fetchTo),
      };
    }
    case "resnap":
      // Keep the calendar window fixed, only re-grid the visible zoom onto a new
      // bucket size — used when the resolution or presentation shifts under us.
      return {
        ...state,
        visibleZoom: zoomFor(state.calendarRange, action.resolution, fetchFrom, fetchTo),
      };
  }
}

const TIME_SLIDER_RESOLUTION: Resolution = "month";

export function useChartState({ fetchFrom, fetchTo }: { fetchFrom: string; fetchTo: string }) {
  const [state, rawDispatch] = useReducer(reducer, undefined, () => ({
    aggregation: "auto" as Aggregation,
    sliderWindow: "year" as SliderWindow,
    visibleZoom: defaultVisibleZoom("month", fetchFrom, fetchTo, "year"),
    calendarRange: calendarRangeForWindow("year", fetchTo, fetchFrom, fetchTo),
  }));

  // Thread the fetch envelope into every action so the reducer stays a pure
  // function of (state, action) without closing over component scope.
  const dispatch = useCallback(
    (action: Action) => rawDispatch({ ...action, fetchFrom, fetchTo }),
    [fetchFrom, fetchTo],
  );

  const setAggregation = useCallback(
    (next: Aggregation) => dispatch({ type: "setAggregation", next }),
    [dispatch],
  );
  const setSliderWindow = useCallback(
    (next: SliderWindow, resolution: Resolution) =>
      dispatch({ type: "setSliderWindow", next, resolution }),
    [dispatch],
  );
  const handleChartVisibleZoom = useCallback(
    (next: VisibleZoom, resolution: Resolution) =>
      dispatch({ type: "chartVisibleZoom", next, resolution }),
    [dispatch],
  );
  const handleSliderVisibleZoom = useCallback(
    (next: VisibleZoom, chartResolution: Resolution, presentation: LightningPresentation) =>
      dispatch({
        type: "sliderVisibleZoom",
        next,
        sliderResolution: TIME_SLIDER_RESOLUTION,
        chartResolution,
        presentation,
      }),
    [dispatch],
  );
  // Re-grid the zoom when the bucket grid shifts (auto resolved differently, or
  // we returned from the map to the chart). The component owns the *trigger*
  // because it watches the live resolution; the reducer owns the cascade.
  const resnap = useCallback(
    (resolution: Resolution) => dispatch({ type: "resnap", resolution }),
    [dispatch],
  );

  // The slider track speaks its own (month) granularity, so the chart's visible
  // window is re-snapped onto the slider grid for display on the overview track.
  const sliderVisibleZoom = useMemo(
    () => zoomFor(state.calendarRange, TIME_SLIDER_RESOLUTION, fetchFrom, fetchTo),
    [state.calendarRange, fetchFrom, fetchTo],
  );

  return {
    aggregation: state.aggregation,
    sliderWindow: state.sliderWindow,
    visibleZoom: state.visibleZoom,
    calendarRange: state.calendarRange,
    sliderVisibleZoom,
    timeSliderResolution: TIME_SLIDER_RESOLUTION,
    setAggregation,
    setSliderWindow,
    handleChartVisibleZoom,
    handleSliderVisibleZoom,
    resnap,
  };
}
