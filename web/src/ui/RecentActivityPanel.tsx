import { useEffect, useRef, useState } from "react";
import { History, MoveHorizontal } from "lucide-react";
import type { RecentActivityData, RecentRecord, SensorId } from "../data/contracts";
import { formatPercent, MODIS_RECORD_NOTE, monthName, Panel, TYPE_FIELD_NOTE } from "./shared";

const MONTHS = Array.from({ length: 12 }, (_, index) => index + 1);

function sourceLabel(source: RecentRecord["source_type"]) {
  if (source === "nrt") return "NRT";
  if (source === "archive") return "Archive";
  if (source === "archive+nrt") return "Archive + NRT";
  return "No source file";
}

function RecentCell({ record }: { record: RecentRecord | undefined }) {
  if (!record || !record.has_data || record.occupied_cell_fraction === null) {
    return (
      <td className="recent-cell missing" title={record?.coverage_note ?? "No record"}>
        <strong>Missing</strong>
        <small>{record?.coverage_note === "outside_downloaded_source_coverage"
          ? "not in downloaded files"
          : record?.coverage_note === "no_detections_after_quality_filtering"
            ? "no detections; not a confirmed zero"
            : "incomplete source coverage"}</small>
      </td>
    );
  }
  const elevated = record.elevated === true;
  return (
    <td className="recent-cell" title={`${record.period} · ${sourceLabel(record.source_type)}`}>
      <strong className={elevated ? "text-orange" : ""}>{formatPercent(record.occupied_cell_fraction, 1)}</strong>
      <span className={`label-pill ${elevated ? "elevated" : "not_elevated"}`}>{elevated ? "elevated" : "not elevated"}</span>
      <small>rank {record.historical_rank}/{record.n_historical_values + 1}{record.n_historical_values_tied ? " (tied)" : ""} · {sourceLabel(record.source_type)}</small>
    </td>
  );
}

export default function RecentActivityPanel({ recent, sensor }: { recent: RecentActivityData; sensor: SensorId }) {
  const block = recent.sensors[sensor];
  const { reference, holdout, recent: recentPeriod } = recent.periods;
  const byPeriod = new Map(block.records.map((record) => [record.period, record]));
  const rowFor = (year: number) => MONTHS.map((month) => byPeriod.get(`${year}-${String(month).padStart(2, "0")}`));
  const holdoutRows = rowFor(holdout.year);
  const recentRows = rowFor(recentPeriod.year);
  const countElevated = (rows: (RecentRecord | undefined)[]) => rows.filter((r) => r?.elevated === true).length;
  const countData = (rows: (RecentRecord | undefined)[]) => rows.filter((r) => r?.has_data).length;
  const missingMonths = (rows: (RecentRecord | undefined)[]) =>
    rows.flatMap((r, index) => (!r || !r.has_data ? [monthName(index + 1, true)] : []));
  const quantile = Math.round(recent.configuration.elevated_quantile * 100);
  const years = reference.end - reference.start + 1;

  // Show a scroll cue only when the table is wider than its container. Without
  // ResizeObserver (e.g. old browsers, jsdom) the cue stays visible.
  const wrapRef = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(true);
  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || typeof ResizeObserver === "undefined") return;
    const update = () => setOverflowing(wrap.scrollWidth > wrap.clientWidth + 1);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [sensor]);

  const periodHeader = (label: string, rows: (RecentRecord | undefined)[]) => {
    const missing = missingMonths(rows);
    return (
      <th scope="row">
        {label}
        <small>{countElevated(rows)} of {countData(rows)} elevated</small>
        {missing.length > 0 ? <small className="recent-missing-summary">Missing: {missing.join(", ")}</small> : null}
      </th>
    );
  };

  return (
    <Panel
      title={`Historical-to-recent activity · ${block.label}`}
      subtitle={`Reference ${reference.start}–${reference.end} (frozen) · ${holdout.year} holdout · ${recentPeriod.year} recent · Convention ${recent.configuration.grid_convention}, ${recent.configuration.grid_resolution_deg}° grid`}
    >
      {overflowing ? (
        <p className="recent-scroll-cue"><MoveHorizontal size={13} aria-hidden="true" />Scroll sideways to see all 12 months (Jan–Dec)</p>
      ) : null}
      <div className="config-table-wrap recent-table-wrap" ref={wrapRef} tabIndex={0} aria-label="Monthly comparison table, scrollable horizontally">
        <table className="data-table recent-table" aria-label={`Occupied-cell fraction of ${holdout.year} and ${recentPeriod.year} compared with the frozen ${reference.start}–${reference.end} reference`}>
          <thead>
            <tr><th scope="col">Period</th>{MONTHS.map((month) => <th key={month} scope="col">{monthName(month, true)}</th>)}</tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Reference median {reference.start}–{reference.end}</th>
              {block.reference.map((ref) => <td key={ref.month}>{formatPercent(ref.baseline_median, 1)}</td>)}
            </tr>
            <tr>
              <th scope="row">Elevated threshold (q{quantile} of {years} years)</th>
              {block.reference.map((ref) => <td key={ref.month}>{formatPercent(ref.elevated_threshold, 1)}</td>)}
            </tr>
            <tr>
              {periodHeader(`${holdout.year} holdout`, holdoutRows)}
              {holdoutRows.map((record, index) => <RecentCell key={index} record={record} />)}
            </tr>
            <tr>
              {periodHeader(`${recentPeriod.year} recent`, recentRows)}
              {recentRows.map((record, index) => <RecentCell key={index} record={record} />)}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="method-note">
        Sensor-specific comparison of the occupied-cell fraction with this sensor&apos;s own frozen {reference.start}–{reference.end} reference.
        The threshold is the {quantile}th percentile of only {years} historical values for the same calendar month, so &ldquo;elevated&rdquo; means
        a high rank against those years ({recent.configuration.historical_rank_definition}). It is not a statistical test, forecast or calibrated
        cross-sensor fusion, and it does not show that the number of fires, burned area or damage increased.
      </p>
      <p className="method-note">
        Rank and threshold answer different questions. The {quantile}th-percentile threshold is interpolated between the {years} historical values
        for that calendar month (with six values it lies between the second- and third-highest), so a month can be elevated while one or two
        historical years were still higher, for example &ldquo;elevated · rank 3/7&rdquo;.
      </p>
      <p className="method-note">
        &ldquo;Elevated&rdquo; = above this month&apos;s frozen threshold; &ldquo;not elevated&rdquo; = at or below it. Archive months use FIRMS archive files; NRT months use
        near-real-time files, which are not reprocessed like the archive and are less comparable with the archive-based reference. &ldquo;Missing&rdquo; means
        no value is reported (outside the downloaded files, or no quality-filtered detections); missing months are not zero activity, and FIRMS
        detection records do not show when the sensor actually observed the area. Values are not comparable between MODIS and VIIRS.
      </p>
      {sensor === "MODIS_C61" ? (
        <p className="method-note recent-sensor-caveat"><strong>MODIS caveat:</strong> {MODIS_RECORD_NOTE}</p>
      ) : (
        <p className="method-note recent-sensor-caveat">
          <strong>VIIRS note:</strong> the VIIRS archive uses one product version (Collection 2) for 2019–2026, and its median daytime detection time stays
          near 13:30–13:45 local time in every year (Stage 6B.1 check). It is not affected by the MODIS collection change or Terra/Aqua drift, but it is a
          different sensor, not a ground truth or an equivalent replacement for MODIS.
        </p>
      )}
      <p className="method-note">{TYPE_FIELD_NOTE}</p>
      <div className="subtle-note">
        <History size={14} aria-hidden="true" />
        <span>Sources: {recent.sources.filter((s) => s.sensor === sensor).map((s) => `${s.filename} (${s.source_type}, ${s.date_min} to ${s.date_max}, SHA-256 ${s.sha256.slice(0, 12)}…)`).join("; ")}</span>
      </div>
    </Panel>
  );
}
