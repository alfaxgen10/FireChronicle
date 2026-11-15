import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { CircleHelp, LoaderCircle, MapPinned, Radio, Signal, ThermometerSun } from "lucide-react";
import { MapContainer, Rectangle, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import type { CellActivityData, FireChronicleData, SensorId } from "../data/contracts";
import { aggregateCells, legendEntries } from "../ui/cellActivity";
import { AOI_LABEL, AOI_NOTE, EmptyState, formatAnomalyLabel, formatNumber, formatPercent, monthName, PageHeader, Panel, SensorSelector, StatCard } from "../ui/shared";

const FireMap = lazy(() => import("../ui/FireMap"));

function FitRegion({ bounds }: { bounds: LatLngBoundsExpression }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [24, 24] });
  }, [map, bounds]);
  return null;
}

export default function ExplorePage({ data, cellActivity = null }: { data: FireChronicleData; cellActivity?: CellActivityData | null }) {
  const [sensor, setSensor] = useState<SensorId>("MODIS_C61");
  const region = data.regions.regions[0];
  const sensorData = data.calendar.sensors[sensor];
  const options = sensorData.months.map((month) => month.period);
  const defaultPeriod = [...sensorData.months].reverse().find((month) => month.has_data)?.period ?? options[options.length - 1] ?? "";
  const [period, setPeriod] = useState(defaultPeriod);
  const month = sensorData.months.find((record) => record.period === period);
  const [selectedCell, setSelectedCell] = useState<number | null>(null);
  const cellTotals = useMemo(
    () => cellActivity && month
      ? aggregateCells(cellActivity, sensor, { years: [month.year], month: month.month })
      : new Map<number, number>(),
    [cellActivity, sensor, month],
  );
  const maxCount = Math.max(0, ...cellTotals.values());
  const cellLabel = (index: number) => {
    if (!cellActivity) return "";
    const [lon, lat] = cellActivity.grid.cells[index];
    const res = cellActivity.grid.resolution_deg;
    return `${Math.abs(lat + res).toFixed(2)}–${Math.abs(lat).toFixed(2)}° S, ${lon.toFixed(2)}–${(lon + res).toFixed(2)}° E`;
  };
  const bounds = useMemo<LatLngBoundsExpression>(
    () => region
      ? [[region.bbox[1], region.bbox[0]], [region.bbox[3], region.bbox[2]]]
      : [[0, 0], [1, 1]],
    [region],
  );
  const center: [number, number] = region
    ? [(region.bbox[1] + region.bbox[3]) / 2, (region.bbox[0] + region.bbox[2]) / 2]
    : [0, 0];
  if (!region) {
    return <EmptyState title="Study area is not available">The regions export does not contain a valid study-area definition.</EmptyState>;
  }

  return (
    <>
      <PageHeader kicker="REGIONAL OBSERVATORY / 01" title="Explore observations" description={`Satellite active-fire detections across the ${AOI_LABEL}. MODIS and VIIRS remain distinct observation records.`}>
        <SensorSelector value={sensor} onChange={(next) => {
          setSensor(next);
          const nextMonths = data.calendar.sensors[next].months;
          const nextPeriod = nextMonths.find((entry) => entry.period === period)
            ?? [...nextMonths].reverse().find((entry) => entry.has_data)
            ?? nextMonths[nextMonths.length - 1];
          setPeriod(nextPeriod?.period ?? "");
        }} />
      </PageHeader>
      <div className="stat-grid three">
        <StatCard label="Selected period" value={period || "No period"} detail={sensorData.label} icon={<Radio size={18} aria-hidden="true" />} tone="teal" />
        <StatCard label="Thermal detections" value={month?.has_data ? formatNumber(month.detection_count) : "No detections"} detail={month?.has_data ? "Filtered active-fire observations" : "Not a confirmed zero-activity month"} icon={<ThermometerSun size={18} aria-hidden="true" />} tone="orange" />
        <StatCard label="Occupied-cell fraction" value={formatPercent(month?.occupied_cell_fraction)} detail={`Convention ${month?.grid_convention ?? "B"} · ${month?.total_eligible_cells ?? "—"} eligible cells`} icon={<Signal size={18} aria-hidden="true" />} tone="blue" />
      </div>
      <div className="explore-grid">
        {cellActivity ? (
          <Panel
            title={`Detections per cell · ${month ? `${monthName(month.month)} ${month.year}` : period}`}
            subtitle={`${sensorData.label} · quality-filtered NASA FIRMS detections on the ${cellActivity.grid.resolution_deg}° grid · ${cellTotals.size} of ${cellActivity.grid.cells.length} cells with detections`}
            className="map-panel"
          >
            <div className="map-wrap explore-firemap" role="region" aria-label={`Map of ${sensorData.label} detections per grid cell for ${period}`}>
              <Suspense fallback={<div className="fm-loading"><LoaderCircle size={18} className="spin" aria-hidden="true" /> Loading map…</div>}>
                <FireMap
                  cells={cellActivity.grid.cells}
                  resolution={cellActivity.grid.resolution_deg}
                  bbox={cellActivity.grid.bbox}
                  totals={cellTotals}
                  selectedCell={selectedCell}
                  onSelectCell={setSelectedCell}
                  sensorColor={sensor === "MODIS_C61" ? "#f28a52" : "#54b8ae"}
                />
              </Suspense>
              <div className="fm-legend" aria-label="Map legend">
                <strong>Detections per cell</strong>
                <div className="fm-legend-scale">
                  {legendEntries(maxCount).map(({ color, from, last }) => (
                    <span key={color}><i style={{ background: color }} aria-hidden="true" />{formatNumber(from)}{last && from < maxCount ? "+" : ""}</span>
                  ))}
                </div>
                <small>Empty cells: no quality-filtered detections (not confirmed zero fire). Dashed line: pilot AOI.</small>
              </div>
            </div>
            <div className="map-caption"><MapPinned size={15} aria-hidden="true" /><span>{selectedCell != null ? `Selected cell ${cellLabel(selectedCell)}: ${formatNumber(cellTotals.get(selectedCell) ?? 0)} detections this month. ` : "Click a cell for its count. "}{AOI_NOTE}</span></div>
          </Panel>
        ) : (
          <Panel title="Pilot AOI analysis extent" subtitle="Regional context · bounding box shown; per-cell data not loaded" className="map-panel">
            <div className="map-wrap" role="region" aria-label={`Interactive map of the ${AOI_LABEL} analysis extent`}>
              <MapContainer center={center} zoom={7} scrollWheelZoom={false} className="leaflet-map">
                <FitRegion bounds={bounds} />
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <Rectangle bounds={bounds} pathOptions={{ color: "#f28a52", weight: 2, fillColor: "#e77e46", fillOpacity: 0.13 }} />
              </MapContainer>
              <div className="map-scale"><span className="legend-outline" /> Analysis bounding box</div>
            </div>
            <div className="map-caption"><MapPinned size={15} aria-hidden="true" /><span>{AOI_LABEL} · {region.bbox[0]}°E to {region.bbox[2]}°E · {Math.abs(region.bbox[3])}°S to {Math.abs(region.bbox[1])}°S · {AOI_NOTE}</span></div>
          </Panel>
        )}
        <div className="stacked-panels">
          <Panel title="Observation controls" subtitle="Filter the sensor series by available archive period">
            <div className="control-block">
              <label className="field-label" htmlFor="period-select">Available month</label>
              <select id="period-select" value={period} onChange={(event) => setPeriod(event.target.value)}>
                {options.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
              <p className="field-hint">The archive includes every month in the declared window. A null value means unavailable/no detections after filtering—not zero activity.</p>
            </div>
            <div className="data-availability">
              <div><span className="availability-dot" /><span>{sensorData.label}</span><strong>{sensorData.available ? "Available" : "Not available"}</strong></div>
              <div><span className="availability-dot soft" /><span>Study period</span><strong>{data.calendar.baseline_window.start}–{data.calendar.baseline_window.end}</strong></div>
            </div>
          </Panel>
          <Panel title="Period summary" subtitle={month ? `${month.period} · ${sensorData.label}` : "No month selected"}>
            {month?.has_data ? (
              <div className="summary-list">
                <div><span>Occupied cells</span><strong>{month.occupied_cells} / {month.total_eligible_cells}</strong></div>
                <div><span>Seasonal baseline</span><strong>{formatPercent(month.baseline_median)}</strong></div>
                <div><span>Anomaly vs. baseline</span><strong className={month.anomaly != null && month.anomaly > 0 ? "text-orange" : ""}>{month.anomaly == null ? "Not evaluated" : `${month.anomaly > 0 ? "+" : ""}${(month.anomaly * 100).toFixed(2)} pp`}</strong></div>
                <div><span>Classification</span><strong>{formatAnomalyLabel(month.anomaly_label)}</strong></div>
              </div>
            ) : <EmptyState title="No filtered observations for this month">{month?.coverage_note || "No data are reported for the selected period."} The absence of detections does not confirm absence of fire activity.</EmptyState>}
            <div className="subtle-note"><CircleHelp size={14} aria-hidden="true" /><span>Hotspots are thermal anomalies—not unique fires, burned area, or severity.</span></div>
          </Panel>
        </div>
      </div>
      <div className="provenance-strip"><span><span className="provenance-mark" /> Export generated {new Date(data.calendar.generated_at).toLocaleString()}</span><span>Contract {data.calendar.contract_version} · Processing {data.calendar.processing_version}</span><span><Signal size={13} aria-hidden="true" /> Spatial resolution {data.calendar.grid_resolution_deg}°</span></div>
    </>
  );
}
