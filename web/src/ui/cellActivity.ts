import type { CellActivityData, SensorId } from "../data/contracts";

export type TimeSelection = { years: number[]; month: number | null };

/** Sum detections per cell for the selected sensor, years and (optionally) one calendar month. */
export function aggregateCells(data: CellActivityData, sensor: SensorId, selection: TimeSelection): Map<number, number> {
  const totals = new Map<number, number>();
  for (const [period, cells] of Object.entries(data.sensors[sensor].periods)) {
    const year = Number(period.slice(0, 4));
    const month = Number(period.slice(5, 7));
    if (!selection.years.includes(year)) continue;
    if (selection.month != null && month !== selection.month) continue;
    for (const [index, count] of cells) totals.set(index, (totals.get(index) ?? 0) + count);
  }
  return totals;
}

/** Years that have at least one month of data for either sensor. */
export function availableYears(data: CellActivityData): number[] {
  const years = new Set<number>();
  for (const sensor of Object.values(data.sensors)) {
    for (const period of Object.keys(sensor.periods)) years.add(Number(period.slice(0, 4)));
  }
  return [...years].sort((a, b) => a - b);
}

/** Latest acquisition date in any source file of the sensor (archive or NRT). */
export function latestObservation(data: CellActivityData, sensor: SensorId): string | null {
  const dates = Object.values(data.sensors[sensor].source_coverage).map(([, end]) => end);
  return dates.length ? dates.sort().at(-1) ?? null : null;
}

/** Five ordered intensity classes, scaled to the selection's maximum (square-root scale). */
export const INTENSITY_COLORS = ["#fde68a", "#fbbf24", "#f97316", "#ea580c", "#b91c1c"];

export function intensityClass(count: number, max: number): number {
  if (max <= 0) return 0;
  const t = Math.sqrt(count / max);
  return Math.min(INTENSITY_COLORS.length - 1, Math.floor(t * INTENSITY_COLORS.length));
}

/**
 * Legend entries with distinct lower bounds. When several classes share a lower bound
 * (small maxima), only the last of them can actually be assigned, so it is the one kept.
 */
export function legendEntries(max: number): Array<{ color: string; from: number; last: boolean }> {
  const breaks = intensityBreaks(max);
  const entries = breaks.flatMap((from, index) =>
    index < breaks.length - 1 && breaks[index + 1] === from ? [] : [{ color: INTENSITY_COLORS[index], from, last: false }]);
  if (entries.length) entries[entries.length - 1].last = true;
  return entries;
}

export function intensityBreaks(max: number): number[] {
  // Lower bound of each class in detections, from the square-root scale.
  return INTENSITY_COLORS.map((_, index) => Math.max(1, Math.ceil(max * (index / INTENSITY_COLORS.length) ** 2)));
}
