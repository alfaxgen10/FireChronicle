import { useMemo, useState } from "react";
import { GitCompareArrows } from "lucide-react";
import type { FireChronicleData, RecentActivityData } from "../data/contracts";
import { buildAgreement, countStates, type AgreementState } from "./agreement";
import { monthName, Panel } from "./shared";

const STATE_LABEL: Record<AgreementState, string> = {
  both: "Elevated in both sensors",
  modis_only: "MODIS only",
  viirs_only: "VIIRS only",
  neither: "Neither elevated",
  missing: "Missing data",
};
const STATE_SHORT: Record<AgreementState, string> = { both: "Both", modis_only: "M", viirs_only: "V", neither: "", missing: "–" };
const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

export default function AgreementCalendar({ data, recent }: { data: FireChronicleData; recent: RecentActivityData | null }) {
  const cells = useMemo(() => buildAgreement(data, recent), [data, recent]);
  const byPeriod = useMemo(() => new Map(cells.map((c) => [c.period, c])), [cells]);
  const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b);
  const baseline = cells.filter((c) => c.basis === "baseline");
  const recentCells = cells.filter((c) => c.basis === "recent");
  const baseCounts = countStates(baseline);
  const recentCounts = countStates(recentCells);
  const [selected, setSelected] = useState<string | null>(null);
  const picked = selected ? byPeriod.get(selected) : undefined;
  const lastBaselineYear = data.calendar.baseline_window.end;

  return (
    <Panel
      title="Cross-sensor agreement calendar"
      subtitle={`Was each month elevated for MODIS, for VIIRS, or for both? Each sensor is judged against its own same-month threshold (primary configuration). ${data.calendar.baseline_window.start}–${lastBaselineYear} in-sample; ${lastBaselineYear + 1} onward against thresholds frozen at ${lastBaselineYear}.`}
      className="agreement-panel"
    >
      <div className="agree-summary">
        <div><strong className="agree-both-text">{baseCounts.both}</strong><span>months elevated in both sensors, {data.calendar.baseline_window.start}–{lastBaselineYear}</span></div>
        <div><strong className="agree-one-text">{baseCounts.modis_only + baseCounts.viirs_only}</strong><span>elevated in one sensor only ({baseCounts.modis_only} MODIS, {baseCounts.viirs_only} VIIRS)</span></div>
        {recentCells.length ? (
          <div><strong className="agree-both-text">{recentCounts.both}</strong><span>months elevated in both, {lastBaselineYear + 1}–{years[years.length - 1]} ({recentCounts.modis_only + recentCounts.viirs_only} in one only, {recentCounts.missing} missing)</span></div>
        ) : null}
      </div>

      <div className="agree-wrap">
        <table className="agree-table">
          <caption className="sr-only">Cross-sensor agreement of elevated months by year and month</caption>
          <thead><tr><th scope="col"><span className="sr-only">Year</span></th>{MONTHS.map((m) => <th key={m} scope="col">{monthName(m, true)}</th>)}</tr></thead>
          <tbody>
            {years.map((year) => (
              <tr key={year} className={year === lastBaselineYear + 1 ? "agree-break" : undefined}>
                <th scope="row">{year}{year > lastBaselineYear ? <small>vs frozen</small> : null}</th>
                {MONTHS.map((m) => {
                  const period = `${year}-${String(m).padStart(2, "0")}`;
                  const cell = byPeriod.get(period);
                  if (!cell) return <td key={m} />;
                  const label = `${monthName(m)} ${year}: ${STATE_LABEL[cell.state]}${cell.stability === "consistently_elevated" ? ", consistently elevated across all tested configurations" : ""}`;
                  return (
                    <td key={m}>
                      <button
                        type="button"
                        className={`agree-cell ${cell.state}${selected === period ? " selected" : ""}`}
                        aria-label={label}
                        aria-pressed={selected === period}
                        title={label}
                        onClick={() => setSelected(selected === period ? null : period)}
                      >
                        {STATE_SHORT[cell.state]}
                        {cell.stability === "consistently_elevated" ? <i className="agree-star" aria-hidden="true">★</i> : null}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="agree-legend" aria-label="Legend">
        {(["both", "modis_only", "viirs_only", "neither", "missing"] as AgreementState[]).map((s) => (
          <span key={s}><i className={`agree-swatch ${s}`} aria-hidden="true">{STATE_SHORT[s]}</i>{STATE_LABEL[s]}</span>
        ))}
        <span><i className="agree-swatch neither" aria-hidden="true"><b className="agree-star">★</b></i>Consistently elevated across all tested configurations</span>
      </div>

      <p className="agree-detail">
        <GitCompareArrows size={15} aria-hidden="true" />
        {picked
          ? <span><strong>{monthName(picked.month)} {picked.year}:</strong> {STATE_LABEL[picked.state]}.{" "}
              {picked.state === "both" ? "Two different sensors agree, so the increase is unlikely to be one instrument's artefact." : null}
              {picked.state === "modis_only" || picked.state === "viirs_only" ? "Only one sensor shows it: treat with caution, it may reflect that sensor's characteristics." : null}
              {picked.state === "missing" ? "No value is reported for at least one sensor; missing is not zero activity." : null}
              {picked.stability ? ` Stability label across configurations: ${picked.stability.replaceAll("_", " ")}.` : ""}</span>
          : <span>Select a month. Agreement between two independent sensors is the strongest evidence that a month was genuinely more active; a one-sensor spike is flagged for caution. Agreement is not calibration, and elevated means a high rank against six years, not more fires or burned area.</span>}
      </p>
    </Panel>
  );
}
