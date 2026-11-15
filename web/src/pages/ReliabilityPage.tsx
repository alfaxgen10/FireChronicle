import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { Activity, CircleAlert, FlaskConical, Layers3, Signal, ShieldCheck } from "lucide-react";
import { SENSOR_IDS, type FireChronicleData, type HarmonizationData, type ReliabilityPeriod } from "../data/contracts";
import { EmptyState, formatConfigName, formatPercent, IN_SAMPLE_NOTE, PageHeader, Panel, RELIABILITY_NOTE, SPEARMAN_NOTE, StatCard } from "../ui/shared";
import ReactECharts from "../ui/charts";
import HarmonizationPanel from "../ui/HarmonizationPanel";

const labelOrder = [
  "consistently_elevated",
  "not_elevated",
  "classification_sensitive",
  "insufficient_evidence",
  "insufficient_cross_sensor_evidence",
];
const labelColors: Record<string, string> = {
  consistently_elevated: "#e98a50",
  not_elevated: "#56b9ad",
  classification_sensitive: "#d8b15f",
  insufficient_evidence: "#66798b",
  insufficient_cross_sensor_evidence: "#788ba1",
};
const textColor = "#a9bacb";
const gridLine = "rgba(147, 168, 188, 0.11)";
const readable = (label: string) => label.replaceAll("_", " ");

function getLabelCounts(periods: ReliabilityPeriod[]) {
  return labelOrder.map((label) => ({
    label,
    count: periods.filter((period) => period.stability_label === label).length,
  })).filter((item) => item.count > 0);
}

export default function ReliabilityPage({ data, harmonization = null }: { data: FireChronicleData; harmonization?: HarmonizationData | null }) {
  const periods = data.reliability.per_period;
  const defaultPeriod = periods.find((period) => period.n_evaluable > 0) ?? periods[0];
  const [selectedPeriod, setSelectedPeriod] = useState(defaultPeriod?.period ?? "");
  const selected = periods.find((period) => period.period === selectedPeriod);
  const configs = Object.entries(data.reliability.configurations);
  const overlap = data.sensors.overlap_diagnostics;
  const labelCounts = useMemo(() => getLabelCounts(periods), [periods]);

  const comparisonOption: EChartsOption = {
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (value) => formatPercent(typeof value === "number" ? value : null) },
    legend: { top: 0, right: 8, textStyle: { color: textColor }, itemWidth: 13, itemHeight: 8 },
    grid: { top: 38, right: 18, bottom: 52, left: 62 },
    xAxis: {
      type: "category",
      data: overlap.detail.map((row) => row.period),
      axisLabel: { color: textColor, rotate: 30, fontSize: 10 },
      axisLine: { lineStyle: { color: gridLine } },
    },
    yAxis: {
      type: "value",
      min: 0,
      axisLabel: { color: textColor, formatter: (value: number) => `${(value * 100).toFixed(2)}%` },
      splitLine: { lineStyle: { color: gridLine } },
    },
    series: [
      { name: "MODIS", type: "line", data: overlap.detail.map((row) => row.modis_ocf), connectNulls: false, symbolSize: 7, lineStyle: { color: "#f28a52", width: 2 }, itemStyle: { color: "#f28a52" } },
      { name: "VIIRS", type: "line", data: overlap.detail.map((row) => row.viirs_ocf), connectNulls: false, symbolSize: 7, lineStyle: { color: "#54b8ae", width: 2 }, itemStyle: { color: "#54b8ae" } },
    ],
  };
  const coverageOption: EChartsOption = selected ? {
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { top: 16, right: 12, bottom: 34, left: 102 },
    xAxis: { type: "value", min: 0, max: Math.max(selected.n_configs_total, 1), axisLabel: { color: textColor }, splitLine: { lineStyle: { color: gridLine } } },
    yAxis: { type: "category", data: ["Configuration coverage"], axisLabel: { color: textColor } },
    series: [
      { name: "Evaluable", type: "bar", stack: "total", data: [selected.n_evaluable], itemStyle: { color: "#4cb4a8" }, label: { show: selected.n_evaluable > 0, position: "inside", color: "#07111f", formatter: "Evaluable" } },
      { name: "Insufficient evidence", type: "bar", stack: "total", data: [selected.n_insufficient], itemStyle: { color: "#65798d" }, label: { show: selected.n_insufficient > 0, position: "inside", color: "#edf4fa", formatter: "Insufficient" } },
      { name: "Not run", type: "bar", stack: "total", data: [selected.n_not_run], itemStyle: { color: "#354657" }, label: { show: selected.n_not_run > 0, position: "inside", color: "#edf4fa", formatter: "Not run" } },
    ],
  } : {};
  const classificationsOption: EChartsOption = {
    animation: false,
    tooltip: { trigger: "item", formatter: (params) => {
      const item = params as { name?: string; value?: number };
      return `${readable(item.name ?? "")}: ${item.value ?? 0} months`;
    } },
    legend: { orient: "horizontal", left: "center", bottom: 0, itemGap: 14, textStyle: { color: textColor, fontSize: 11 }, formatter: readable },
    series: [{
      type: "pie",
      radius: ["46%", "66%"],
      center: ["50%", "42%"],
      label: { show: false },
      data: labelCounts.map(({ label, count }) => ({ name: label, value: count, itemStyle: { color: labelColors[label] ?? "#66798b" } })),
    }],
  };

  return (
    <>
      <PageHeader kicker="SENSITIVITY ANALYSIS / 03" title="Reliability lab" description="Cross-sensor classification stability and sensitivity across the declared configuration registry—not a probability that any classification is correct.">
        <label className="field-control" htmlFor="reliability-period">
          <span className="sr-only">Select month for reliability detail</span>
          <select id="reliability-period" value={selectedPeriod} onChange={(event) => setSelectedPeriod(event.target.value)}>
            {periods.map((period) => <option key={period.period} value={period.period}>{period.period}</option>)}
          </select>
        </label>
      </PageHeader>
      <div className="stat-grid three">
        <StatCard label="Declared configurations" value={String(configs.length)} detail={`Registry version ${data.reliability.config_registry_version} · ${data.reliability.config_registry_history[String(data.reliability.config_registry_version)]?.length ?? configs.length} active`} icon={<Layers3 size={18} aria-hidden="true" />} tone="teal" />
        <StatCard label="Selected period coverage" value={selected ? `${selected.n_evaluable} / ${selected.n_configs_total}` : "—"} detail={selected ? `${formatPercent(selected.evaluable_fraction)} evaluable · ${selected.min_evaluable_required} required` : "No selected period"} icon={<Signal size={18} aria-hidden="true" />} tone="orange" />
        <StatCard label="Cross-sensor evidence" value={selected?.cross_sensor_requirement_met ? "Rule met" : "Not met"} detail={selected?.sensors_lacking_evaluable_config.length ? `Missing: ${selected.sensors_lacking_evaluable_config.join(", ")}` : "Requires evidence from both sensors"} icon={<ShieldCheck size={18} aria-hidden="true" />} tone="blue" />
      </div>
      <div className="reliability-grid">
        <Panel title="MODIS–VIIRS comparison" subtitle={`Occupied-cell fraction · ${overlap.n_overlap_months} overlapping months`}>
          {overlap.detail.length > 0
            ? <ReactECharts aria-label="MODIS and VIIRS occupied-cell fraction comparison" option={comparisonOption} style={{ height: 276 }} opts={{ renderer: "canvas" }} />
            : <EmptyState title="No overlapping observations">{overlap.harmonization_note}</EmptyState>}
          <div className="subtle-note"><CircleAlert size={14} aria-hidden="true" /><span>Series are kept separate. An observed ratio is not a sensor calibration factor. {SPEARMAN_NOTE}</span></div>
        </Panel>
        <Panel title="Period classification" subtitle={`Distribution across ${periods.length} records`}>
          {labelCounts.length > 0
            ? <ReactECharts aria-label="Distribution of reliability classifications" option={classificationsOption} style={{ height: 276 }} opts={{ renderer: "canvas" }} />
            : <EmptyState title="No classifications available">No period records were provided by the reliability export.</EmptyState>}
          <div className="chart-caption">Labels represent stability/evaluability states; insufficient evidence is not evidence of no activity.</div>
          <div className="chart-caption">{IN_SAMPLE_NOTE} Agreement across configurations shows stability, not correctness.</div>
          <div className="chart-caption">{RELIABILITY_NOTE}</div>
        </Panel>
      </div>
      {harmonization ? <HarmonizationPanel harmonization={harmonization} /> : null}
      <div className="reliability-grid">
        <Panel title={`Configuration coverage · ${selectedPeriod}`} subtitle="Only evaluable results count toward agreement">
          {selected ? (
            <>
              <ReactECharts aria-label="Selected period evaluable, insufficient, and not-run configuration counts" option={coverageOption} style={{ height: 112 }} opts={{ renderer: "canvas" }} />
              <div className="coverage-summary">
                <span><i className="dot teal" /> Evaluable <strong>{selected.n_evaluable}</strong></span>
                <span><i className="dot slate" /> Insufficient <strong>{selected.n_insufficient}</strong></span>
                <span><i className="dot dark" /> Not run <strong>{selected.n_not_run}</strong></span>
              </div>
              <div className="classification-result">
                <span>Cross-sensor stability label</span>
                <strong className={`label-pill ${selected.stability_label}`}>{readable(selected.stability_label)}</strong>
                <small>{data.reliability.stability_labels[selected.stability_label] ?? "No label description was provided."}</small>
              </div>
            </>
          ) : <EmptyState title="No period selected">Choose an available period to inspect configuration coverage.</EmptyState>}
        </Panel>
        <Panel title="Sensor-specific findings" subtitle="Single-sensor results are not cross-sensor agreement">
          {selected ? (
            <div className="sensor-findings">
              {SENSOR_IDS.map((id) => {
                const result = selected.sensor_specific[id];
                return (
                <div className="sensor-finding" key={id}>
                  <div className="sensor-finding-head"><span className={`sensor-swatch ${id === "MODIS_C61" ? "modis" : "viirs"}`} /><strong>{id === "MODIS_C61" ? "MODIS" : "VIIRS"}</strong><span className={`label-pill ${result.label}`}>{readable(result.label)}</span></div>
                  <div className="finding-metrics"><span>{result.n_evaluable} / {result.n_configs} evaluable</span><span>{result.n_elevated} elevated</span><span>{result.n_not_elevated} not elevated</span></div>
                  <small>{data.reliability.sensor_specific_labels[result.label] ?? "No sensor-specific description was provided."}</small>
                </div>
                );
              })}
            </div>
          ) : <EmptyState title="No period selected">Sensor-level findings are reported when a month is selected.</EmptyState>}
        </Panel>
      </div>
      <Panel title="Predefined reliability configurations" subtitle="Registry supplied by the scientific export; configuration count and values are data-driven">
        <div className="config-table-wrap">
          <table className="data-table">
            <thead><tr><th>Configuration</th><th>Sensor</th><th>Grid</th><th>Baseline</th><th>Threshold</th><th>Convention</th></tr></thead>
            <tbody>{configs.map(([name, config]) => (
              <tr key={name}>
                <td><span className="config-name"><FlaskConical size={14} aria-hidden="true" />{formatConfigName(name)}</span></td>
                <td>{config.sensor === "MODIS_C61" ? "MODIS" : "VIIRS"}</td>
                <td>{config.grid_deg}°</td>
                <td>{config.baseline_start}–{config.baseline_end}</td>
                <td>{(config.elevated_quantile * 100).toFixed(0)}th percentile</td>
                <td>{config.grid_convention}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="subtle-note"><Activity size={14} aria-hidden="true" /><span>Analytical stability is not a probability of correctness. Configurations sharing a sensor are not independent confirmations.</span></div>
      </Panel>
      <div className="warning-inline"><CircleAlert size={16} aria-hidden="true" /><span>{data.reliability.limitations[0] ?? "Reliability estimates have analytical limitations."}</span></div>
    </>
  );
}
