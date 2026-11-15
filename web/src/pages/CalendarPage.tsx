import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { CalendarRange, ChartNoAxesCombined, Grid2X2, Info } from "lucide-react";
import type { CalendarMonth, FireChronicleData, RecentActivityData, SensorId } from "../data/contracts";
import RecentActivityPanel from "../ui/RecentActivityPanel";
import AgreementCalendar from "../ui/AgreementCalendar";
import { formatAnomalyLabel, formatNumber, formatPercent, IN_SAMPLE_NOTE, monthName, PageHeader, Panel, SensorSelector, StatCard } from "../ui/shared";
import ReactECharts from "../ui/charts";

const chartText = "#a9bacb";
const gridLine = "rgba(147, 168, 188, 0.11)";
const yearRange = (start: number, end: number) => Array.from({ length: end - start + 1 }, (_, index) => start + index);

export default function CalendarPage({ data, recent = null }: { data: FireChronicleData; recent?: RecentActivityData | null }) {
  const [sensor, setSensor] = useState<SensorId>("MODIS_C61");
  const months = data.calendar.sensors[sensor].months;
  const activeDefault = months.find((month) => month.has_data) ?? months[months.length - 1];
  const [selectedPeriod, setSelectedPeriod] = useState(activeDefault?.period ?? "");
  const recordByPeriod = useMemo(() => new Map(months.map((month) => [month.period, month])), [months]);
  const selected: CalendarMonth | undefined = recordByPeriod.get(selectedPeriod);
  const years = yearRange(data.calendar.baseline_window.start, data.calendar.baseline_window.end);
  const yearRows = years.map((year) => months.filter((month) => month.year === year));
  const heatData = yearRows.flatMap((row, yearIndex) => row.map((month) => ({
    value: [month.month - 1, yearIndex, month.occupied_cell_fraction ?? -1],
    period: month.period,
  })));
  const maximumIndex = months.reduce(
    (maximum, month) => Math.max(maximum, month.occupied_cell_fraction ?? 0),
    0,
  );
  const heatOption: EChartsOption = {
    animation: false,
    tooltip: {
      trigger: "item",
      formatter: (raw) => {
        const point = raw as { data?: { period?: string; value?: number[] } };
        const month = point.data?.period ? recordByPeriod.get(point.data.period) : undefined;
        if (!month) return "";
        return `<strong>${month.period}</strong><br/>Occupied-cell fraction: ${formatPercent(month.occupied_cell_fraction)}<br/>${month.has_data ? `${formatNumber(month.detection_count)} detections` : "No filtered detections / unavailable"}`;
      },
    },
    grid: { top: 12, right: 12, bottom: 44, left: 62 },
    xAxis: {
      type: "category",
      data: Array.from({ length: 12 }, (_, index) => monthName(index + 1, true)),
      axisLabel: { color: chartText, fontSize: 11 },
      axisLine: { lineStyle: { color: gridLine } },
      splitArea: { show: true, areaStyle: { color: ["transparent", "rgba(255,255,255,0.012)"] } },
    },
    yAxis: {
      type: "category",
      data: years.map(String),
      axisLabel: { color: chartText, fontSize: 11 },
      axisLine: { lineStyle: { color: gridLine } },
      splitArea: { show: true, areaStyle: { color: ["transparent", "rgba(255,255,255,0.012)"] } },
    },
    visualMap: {
      show: false,
      min: 0,
      max: maximumIndex > 0 ? maximumIndex : 1,
      inRange: { color: ["#163644", "#257a79", "#e9874e", "#f7b76b"] },
      outOfRange: { color: ["#202e3c"] },
    },
    series: [{
      type: "heatmap",
      data: heatData,
      itemStyle: {
        borderColor: "#0d1926",
        borderWidth: 3,
        borderRadius: 3,
      },
      emphasis: { itemStyle: { borderColor: "#f6a66f", borderWidth: 2 } },
    }],
  };
  const trendOption: EChartsOption = {
    animation: false,
    tooltip: {
      trigger: "axis",
      valueFormatter: (value) => formatPercent(typeof value === "number" ? value : null),
    },
    legend: { top: 0, right: 8, textStyle: { color: chartText }, itemWidth: 12, itemHeight: 8 },
    grid: { top: 38, right: 16, bottom: 52, left: 62 },
    xAxis: {
      type: "category",
      data: months.map((month) => month.period),
      axisLabel: { color: chartText, rotate: 35, interval: 11, fontSize: 10 },
      axisLine: { lineStyle: { color: gridLine } },
    },
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: chartText, formatter: (value: number) => `${(value * 100).toFixed(1)}%` },
      splitLine: { lineStyle: { color: gridLine } },
    },
    series: [
      {
        name: "Observed index",
        type: "line",
        data: months.map((month) => ({
          value: month.occupied_cell_fraction,
          symbolSize: month.period === selectedPeriod ? 9 : 5,
          itemStyle: month.period === selectedPeriod ? { color: "#f7a166", borderColor: "#ffe0c4", borderWidth: 2 } : undefined,
        })),
        connectNulls: false,
        showSymbol: true,
        symbolSize: 5,
        lineStyle: { color: "#f28a52", width: 2 },
        itemStyle: { color: "#f28a52" },
      },
      {
        name: "Seasonal baseline",
        type: "line",
        data: months.map((month) => month.baseline_median),
        connectNulls: false,
        showSymbol: false,
        lineStyle: { color: "#51b9ae", width: 1.5, type: "dashed" },
        itemStyle: { color: "#51b9ae" },
      },
    ],
  };

  const handleHeatClick = (event: unknown) => {
    if (typeof event === "object" && event !== null && "data" in event) {
      const point = event as { data?: { period?: string } };
      if (point.data?.period) setSelectedPeriod(point.data.period);
    }
  };

  return (
    <>
      <PageHeader kicker="ARCHIVE / SEASONAL SIGNALS" title="Historical calendar" description="Monthly occupied-cell fraction and seasonal context for the selected sensor. Select a cell to inspect its observations and sensitivity comparison.">
        <div className="calendar-controls">
          <SensorSelector value={sensor} onChange={(next) => {
            setSensor(next);
            const nextMonths = data.calendar.sensors[next].months;
            setSelectedPeriod((nextMonths.find((month) => month.has_data) ?? nextMonths[0])?.period ?? "");
          }} />
          <label className="field-control" htmlFor="calendar-period">
            <span className="sr-only">Select month to inspect</span>
            <select id="calendar-period" value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)}>
              {months.map((month) => <option key={month.period} value={month.period}>{month.period}</option>)}
            </select>
          </label>
        </div>
      </PageHeader>
      <AgreementCalendar data={data} recent={recent} />
      <div className="stat-grid three">
        <StatCard label="Archive window" value={`${years[0] ?? "—"} — ${years[years.length - 1] ?? "—"}`} detail="Declared seasonal baseline period" icon={<CalendarRange size={18} aria-hidden="true" />} tone="teal" />
        <StatCard label="Selected month" value={selected ? `${monthName(selected.month)} ${selected.year}` : "—"} detail={selected?.has_data ? `${formatNumber(selected.detection_count)} filtered detections` : "No detections / unavailable"} icon={<ChartNoAxesCombined size={18} aria-hidden="true" />} tone="orange" />
        <StatCard label="Index convention" value={`Convention ${selected?.grid_convention ?? data.calendar.primary_grid_convention}`} detail={`${selected?.total_eligible_cells ?? "—"} eligible grid cells`} icon={<Grid2X2 size={18} aria-hidden="true" />} tone="blue" />
      </div>
      <div className="calendar-grid">
        <Panel title="Year × month activity index" subtitle={`Occupied-cell fraction · ${data.calendar.sensors[sensor].label}`} className="calendar-heatmap">
          <div className="heatmap-legend" aria-label="Heatmap legend">
            <span>Lower index</span><i className="legend-gradient" /><span>Higher index</span><span className="legend-missing"><i /> Missing / no filtered observations</span>
          </div>
          <ReactECharts aria-label="Monthly occupied-cell fraction heatmap by year" option={heatOption} onEvents={{ click: handleHeatClick }} style={{ height: 282 }} opts={{ renderer: "canvas" }} />
          <div className="subtle-note"><Info size={14} aria-hidden="true" /><span>Null periods are shown separately—not encoded as zero. Click any month to update the linked trend and detail panel.</span></div>
          {sensor === "MODIS_C61" ? (
            <div className="subtle-note"><Info size={14} aria-hidden="true" /><span>MODIS 2019–2022 is Collection 6 and 2023 onward Collection 6.1, and Terra/Aqua observation times drift over the record; compare years with care (see Methodology &amp; export → Data limitations).</span></div>
          ) : null}
          <div className="subtle-note"><Info size={14} aria-hidden="true" /><span>Includes detections that FIRMS flags as static land, offshore or volcano sources (the archive <code>type</code> field is not filtered).</span></div>
        </Panel>
        <Panel title="Selected month detail" subtitle={selected?.period ?? "Select a month"}>
          {selected ? (
            <>
              <div className="detail-emphasis">
                <span>Occupied-cell fraction</span>
                <strong>{formatPercent(selected.occupied_cell_fraction, 3)}</strong>
                <small>Primary Convention B · index is not burned area or fire count</small>
              </div>
              <div className="summary-list">
                <div><span>Detections</span><strong>{selected.has_data ? formatNumber(selected.detection_count) : "No detections"}</strong></div>
                <div><span>Seasonal baseline median</span><strong>{formatPercent(selected.baseline_median, 3)}</strong></div>
                <div><span>Anomaly</span><strong className={selected.anomaly != null && selected.anomaly > 0 ? "text-orange" : ""}>{selected.anomaly == null ? "Insufficient evidence" : `${selected.anomaly > 0 ? "+" : ""}${(selected.anomaly * 100).toFixed(3)} pp`}</strong></div>
                <div><span>Elevated threshold</span><strong>{formatPercent(selected.elevated_threshold, 3)}</strong></div>
                <div><span>Classification</span><strong className={`label-pill ${selected.anomaly_label}`}>{formatAnomalyLabel(selected.anomaly_label)}</strong></div>
                <div><span>Convention A sensitivity</span><strong>{formatPercent(selected.occupied_cell_fraction_convention_a, 3)}</strong></div>
              </div>
              <p className="method-note">The occupied-cell fraction is an unweighted ratio of eligible grid cells. It is not area-weighted, burned area, or a count of unique fires.</p>
              <p className="method-note">{IN_SAMPLE_NOTE}</p>
            </>
          ) : <p className="muted">No record exists for this period.</p>}
        </Panel>
      </div>
      <Panel title="Historical activity trend" subtitle={`${data.calendar.sensors[sensor].label} · observed index and seasonal baseline · selected period highlighted`}>
        <ReactECharts aria-label="Observed monthly occupied-cell fraction compared with seasonal baseline" option={trendOption} style={{ height: 292 }} opts={{ renderer: "canvas" }} />
      </Panel>
      {recent ? <RecentActivityPanel recent={recent} sensor={sensor} /> : null}
      <div className="calendar-footnote"><span><span className="provenance-mark" /> Seasonal comparison uses same-calendar-month medians.</span><span>Baseline: {data.calendar.baseline_window.start}–{data.calendar.baseline_window.end}</span><span>Activity index only; not burned area.</span></div>
    </>
  );
}
