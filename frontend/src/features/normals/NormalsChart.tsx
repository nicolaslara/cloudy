import { useChart } from "../../lib/useChart";
import type { CloudComparisonOption } from "./cloudComparisonOption";
import type { CloudNormalsOption } from "./cloudNormalsOption";
import type { LightningNormalsOption } from "./lightningNormalsOption";

// A normal has no zoomable time axis — it's a single recurring year — so this is
// the thinnest possible renderer: hand useECharts a pre-built option and let it
// mount/patch the canvas. It owns no fetching and no state; the parent decides
// what to draw and which message to show.
export function NormalsChart({
  option,
  structureKey,
  loading,
  error,
  empty,
  emptyMessage,
}: {
  option: CloudNormalsOption | LightningNormalsOption | CloudComparisonOption | null;
  structureKey: string;
  loading: boolean;
  error: Error | null;
  empty: boolean;
  emptyMessage: string;
}) {
  // The generic chart hook is itself typed over the option, so a normals option
  // flows straight through — no exploration types, no widening cast.
  const { containerRef } = useChart(option, structureKey);

  return (
    <div className="chart-area">
      <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
      {loading && <p className="chart-state">Loading normals…</p>}
      {error && (
        <p className="chart-state chart-error">
          Could not load normals. Try again in a moment.
        </p>
      )}
      {empty && !loading && !error && <p className="chart-state">{emptyMessage}</p>}
    </div>
  );
}
