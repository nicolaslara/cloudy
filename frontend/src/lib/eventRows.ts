export type LightningEventPoint = {
  lon: number;
  lat: number;
  peakKa: number;
  cg: boolean;
  ts: number;
  day: string;
};

export function parseEventRows(rows: [number, number, number, number, number][]): LightningEventPoint[] {
  return rows.map(([lon, lat, peakKa, cg, ts]) => ({
    lon,
    lat,
    peakKa,
    cg: cg === 1,
    ts,
    day: new Date(ts * 1000).toISOString().slice(0, 10),
  }));
}

export function dailyCounts(points: LightningEventPoint[]): { day: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const point of points) {
    counts.set(point.day, (counts.get(point.day) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, count]) => ({ day, count }));
}

export function listDays(from: string, to: string): string[] {
  const days: string[] = [];
  const cursor = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  while (cursor.getTime() <= end.getTime()) {
    days.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return days;
}

export function filterByDayRange(
  points: LightningEventPoint[],
  from: string,
  to: string,
): LightningEventPoint[] {
  return points.filter((point) => point.day >= from && point.day <= to);
}

/** RGBA stroke/fill tuned for the dark basemap. */
export function strokeColor(point: LightningEventPoint): [number, number, number, number] {
  return point.cg ? [255, 168, 48, 195] : [96, 176, 255, 175];
}

/** Tooltip HTML for one stroke (dark-map styling lives with the markup). */
export function strokeTooltipHtml(point: LightningEventPoint): string {
  const when = new Date(point.ts * 1000).toISOString().replace("T", " ").slice(0, 16);
  const kind = point.cg ? "Cloud-to-ground" : "Cloud discharge";
  const ka = Math.abs(point.peakKa).toFixed(1);
  const sign = point.peakKa < 0 ? "−" : "+";
  return `<strong>${kind}</strong><br/>${when} UTC<br/>Peak current: ${sign}${ka} kA`;
}
