import type { FireChronicleData, RecentActivityData, SensorId } from "../data/contracts";

export type AgreementState = "both" | "modis_only" | "viirs_only" | "neither" | "missing";

export type AgreementCell = {
  period: string;
  year: number;
  month: number;
  state: AgreementState;
  /** Cross-configuration stability label (2019–2024 only). */
  stability: string | null;
  /** "baseline" = in-sample 2019–2024; "recent" = 2025–2026 against frozen thresholds. */
  basis: "baseline" | "recent";
};

function combine(modis: boolean | null, viirs: boolean | null): AgreementState {
  if (modis == null || viirs == null) return "missing";
  if (modis && viirs) return "both";
  if (modis) return "modis_only";
  if (viirs) return "viirs_only";
  return "neither";
}

/**
 * Per-month agreement between the two sensors' elevated classifications, each against
 * its own same-month threshold (primary configuration). Nothing is recomputed: 2019–2024
 * uses calendar.json `is_elevated`, 2025–2026 uses recent_activity.json `elevated`.
 */
export function buildAgreement(data: FireChronicleData, recent: RecentActivityData | null): AgreementCell[] {
  const cells: AgreementCell[] = [];
  const stability = new Map(data.reliability.per_period.map((p) => [p.period, p.stability_label]));
  const elevatedFromCalendar = (sensor: SensorId) =>
    new Map(data.calendar.sensors[sensor].months.map((m) => [m.period, m.has_data ? m.is_elevated : null] as const));
  const modis = elevatedFromCalendar("MODIS_C61");
  const viirs = elevatedFromCalendar("VIIRS_J1_C2");
  for (const m of data.calendar.sensors.MODIS_C61.months) {
    cells.push({
      period: m.period, year: m.year, month: m.month, basis: "baseline",
      state: combine(modis.get(m.period) ?? null, viirs.get(m.period) ?? null),
      stability: stability.get(m.period) ?? null,
    });
  }
  if (recent) {
    const recentBy = (sensor: SensorId) =>
      new Map(recent.sensors[sensor].records.map((r) => [r.period, r.has_data ? r.elevated : null] as const));
    const rm = recentBy("MODIS_C61");
    const rv = recentBy("VIIRS_J1_C2");
    for (const r of recent.sensors.MODIS_C61.records) {
      cells.push({
        period: r.period, year: r.year, month: r.month, basis: "recent",
        state: combine(rm.get(r.period) ?? null, rv.get(r.period) ?? null),
        stability: null,
      });
    }
  }
  return cells.sort((a, b) => a.period.localeCompare(b.period));
}

export function countStates(cells: AgreementCell[]): Record<AgreementState, number> {
  const counts: Record<AgreementState, number> = { both: 0, modis_only: 0, viirs_only: 0, neither: 0, missing: 0 };
  for (const cell of cells) counts[cell.state] += 1;
  return counts;
}
