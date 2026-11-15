import { lazy, Suspense, useMemo, useState } from "react";
import { Crosshair, LoaderCircle, MapPinned, X } from "lucide-react";
import { SENSOR_IDS, type CellActivityData, type SensorId } from "../data/contracts";
import { aggregateCells, availableYears, latestObservation, legendEntries, type TimeSelection } from "./cellActivity";
import { formatNumber, monthName } from "./shared";

const FireMap = lazy(() => import("./FireMap"));

const SENSOR_COLOR: Record<SensorId, string> = { MODIS_C61: "#f28a52", VIIRS_J1_C2: "#54b8ae" };
const SENSOR_NAME: Record<SensorId, string> = { MODIS_C61: "MODIS", VIIRS_J1_C2: "VIIRS" };

type RangeKey = "baseline" | `${number}`;

export default function FireMapSection({ cellActivity, baselineStart, baselineEnd }: {
  cellActivity: CellActivityData;
  baselineStart: number;
  baselineEnd: number;
}) {
  const [sensor, setSensor] = useState<SensorId>("VIIRS_J1_C2");
  const [range, setRange] = useState<RangeKey>("baseline");
  const [month, setMonth] = useState<number | null>(null);
  const [selectedCell, setSelectedCell] = useState<number | null>(null);
  const years = useMemo(() => availableYears(cellActivity), [cellActivity]);
  const selection: TimeSelection = useMemo(() => ({
    years: range === "baseline" ? years.filter((y) => y >= baselineStart && y <= baselineEnd) : [Number(range)],
    month,
  }), [range, month, years, baselineStart, baselineEnd]);

  const totalsBySensor = useMemo(
    () => Object.fromEntries(SENSOR_IDS.map((id) => [id, aggregateCells(cellActivity, id, selection)])) as Record<SensorId, Map<number, number>>,
    [cellActivity, selection],
  );
  const totals = totalsBySensor[sensor];
  const sum = (map: Map<number, number>) => [...map.values()].reduce((a, b) => a + b, 0);
  const max = Math.max(0, ...totals.values());
  const nCells = cellActivity.grid.cells.length;
  const top = [...totals.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  const cellLabel = (index: number) => {
    const [lon, lat] = cellActivity.grid.cells[index];
    const res = cellActivity.grid.resolution_deg;
    return `${Math.abs(lat + res).toFixed(2)}–${Math.abs(lat).toFixed(2)}° S · ${lon.toFixed(2)}–${(lon + res).toFixed(2)}° E`;
  };
  const rangeLabel = `${range === "baseline" ? `${baselineStart}–${baselineEnd}` : range}${month ? ` · ${monthName(month)}` : " · all months"}`;
  const latest = latestObservation(cellActivity, sensor);
  const nrtStart = cellActivity.sensors[sensor].source_coverage.nrt?.[0];
  const nrtRange = range !== "baseline" && nrtStart != null && Number(range) >= Number(nrtStart.slice(0, 4));

  return (
    <section className="fm" aria-labelledby="fire-map-title">
      <div className="fm-toolbar">
        <div className="fm-title">
          <h2 id="fire-map-title">Regional detection map</h2>
          <span>Quality-filtered NASA FIRMS detections per 0.25° cell · {rangeLabel}</span>
        </div>
        <div className="fm-controls">
          <div className="fm-seg" role="group" aria-label="Sensor">
            {SENSOR_IDS.map((id) => (
              <button key={id} type="button" aria-pressed={sensor === id} className={sensor === id ? "active" : ""} onClick={() => { setSensor(id); setSelectedCell(null); }}>
                <i style={{ background: SENSOR_COLOR[id] }} aria-hidden="true" />{SENSOR_NAME[id]}
              </button>
            ))}
          </div>
          <label className="sr-only" htmlFor="fm-range">Years</label>
          <select id="fm-range" value={range} onChange={(event) => { setRange(event.target.value as RangeKey); setSelectedCell(null); }}>
            <option value="baseline">{baselineStart}–{baselineEnd} (baseline)</option>
            {years.map((year) => <option key={year} value={String(year)}>{year}{year > baselineEnd ? " (after baseline)" : ""}</option>)}
          </select>
          <label className="sr-only" htmlFor="fm-month">Month</label>
          <select id="fm-month" value={month ?? ""} onChange={(event) => { setMonth(event.target.value ? Number(event.target.value) : null); setSelectedCell(null); }}>
            <option value="">All months</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{monthName(m)}</option>)}
          </select>
        </div>
      </div>

      <div className="fm-body">
        <div className="fm-map">
          <Suspense fallback={<div className="fm-loading"><LoaderCircle size={18} className="spin" aria-hidden="true" /> Loading map…</div>}>
            <FireMap
              cells={cellActivity.grid.cells}
              resolution={cellActivity.grid.resolution_deg}
              bbox={cellActivity.grid.bbox}
              totals={totals}
              selectedCell={selectedCell}
              onSelectCell={setSelectedCell}
              sensorColor={SENSOR_COLOR[sensor]}
            />
          </Suspense>
          <div className="fm-legend" aria-label="Map legend">
            <strong>{SENSOR_NAME[sensor]} detections per cell</strong>
            <div className="fm-legend-scale">
              {legendEntries(max).map(({ color, from, last }) => (
                <span key={color}><i style={{ background: color }} aria-hidden="true" />{formatNumber(from)}{last && from < max ? "+" : ""}</span>
              ))}
            </div>
            <small>Empty cells: no quality-filtered detections (not confirmed zero fire). Dashed line: pilot AOI.</small>
          </div>
          <div className="fm-badge">Historical archive · not a live alert map</div>
        </div>

        <aside className="fm-panel" aria-label="Selection summary">
          <div className="fm-stat-grid">
            {SENSOR_IDS.map((id) => (
              <div key={id} className={`fm-stat${id === sensor ? " active" : ""}`}>
                <span><i style={{ background: SENSOR_COLOR[id] }} aria-hidden="true" />{SENSOR_NAME[id]} detections</span>
                <strong>{formatNumber(sum(totalsBySensor[id]))}</strong>
                <small>{totalsBySensor[id].size} of {nCells} cells with detections</small>
              </div>
            ))}
          </div>
          <p className="fm-note">Counts of satellite detections, not fires. VIIRS (375 m pixels) detects more small fires than MODIS (1 km), so the two counts are not comparable.</p>

          {selectedCell != null ? (
            <div className="fm-cell">
              <div className="fm-cell-head"><Crosshair size={15} aria-hidden="true" /><strong>Selected cell</strong><button type="button" className="fm-close" aria-label="Clear selected cell" onClick={() => setSelectedCell(null)}><X size={14} aria-hidden="true" /></button></div>
              <small>{cellLabel(selectedCell)}</small>
              <dl>
                {SENSOR_IDS.map((id) => <div key={id}><dt>{SENSOR_NAME[id]}</dt><dd>{formatNumber(totalsBySensor[id].get(selectedCell) ?? 0)} detections</dd></div>)}
              </dl>
            </div>
          ) : (
            <div className="fm-top">
              <strong>Most active cells · {SENSOR_NAME[sensor]}</strong>
              {top.length ? (
                <ol>
                  {top.map(([index, count]) => (
                    <li key={index}><button type="button" onClick={() => setSelectedCell(index)}><span>{cellLabel(index)}</span><b>{formatNumber(count)}</b></button></li>
                  ))}
                </ol>
              ) : <p className="fm-note">No quality-filtered detections in this selection.</p>}
              <small className="fm-hint"><MapPinned size={13} aria-hidden="true" /> Select a cell on the map for both sensors' counts.</small>
            </div>
          )}

          <dl className="fm-meta">
            <div><dt>Latest observation in data</dt><dd>{latest ?? "—"}</dd></div>
            <div><dt>Source</dt><dd>{nrtRange ? "FIRMS archive + near-real-time (NRT)" : "FIRMS archive"}</dd></div>
          </dl>
        </aside>
      </div>
    </section>
  );
}
