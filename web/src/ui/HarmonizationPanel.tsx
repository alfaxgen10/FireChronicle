import type { EChartsOption } from "echarts";
import { Scale } from "lucide-react";
import type { HarmonizationData } from "../data/contracts";
import ReactECharts from "./charts";
import { Panel } from "./shared";

const METHOD_KEYS = ["A_seasonal", "B_global", "C_climatology"] as const;
const METHOD_LABEL: Record<(typeof METHOD_KEYS)[number], string> = {
  A_seasonal: "Monthly ratio",
  B_global: "Single ratio",
  C_climatology: "No VIIRS (seasonal average)",
};
const METHOD_COLOR: Record<(typeof METHOD_KEYS)[number], string> = {
  A_seasonal: "#54b8ae",
  B_global: "#84aad1",
  C_climatology: "#66798b",
};
const textColor = "#a9bacb";
const gridLine = "rgba(147, 168, 188, 0.11)";

/** Mean absolute error of an occupied-cell fraction, shown in percentage points. */
export function formatPp(value: number) {
  return `${(value * 100).toFixed(1)} pp`;
}

export default function HarmonizationPanel({ harmonization }: { harmonization: HarmonizationData }) {
  const years = Object.keys(harmonization.mae_by_year).sort();
  const nFolds = years.length;
  const option: EChartsOption = {
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (value) => (typeof value === "number" ? formatPp(value) : "—") },
    legend: { top: 0, right: 8, textStyle: { color: textColor }, itemWidth: 12, itemHeight: 8 },
    grid: { top: 36, right: 14, bottom: 30, left: 54 },
    xAxis: { type: "category", data: years, axisLabel: { color: textColor }, axisLine: { lineStyle: { color: gridLine } } },
    yAxis: { type: "value", min: 0, axisLabel: { color: textColor, formatter: (value: number) => `${(value * 100).toFixed(0)} pp` }, splitLine: { lineStyle: { color: gridLine } } },
    series: METHOD_KEYS.map((key) => ({
      name: METHOD_LABEL[key],
      type: "bar" as const,
      data: years.map((year) => harmonization.mae_by_year[year][key]),
      itemStyle: { color: METHOD_COLOR[key], borderRadius: [3, 3, 0, 0] },
      barGap: "12%",
    })),
  };

  return (
    <Panel
      title="Harmonization evaluation · can VIIRS predict MODIS?"
      subtitle={`Leave-one-year-out test, ${years[0]}–${years[years.length - 1]}: each year is predicted from the other ${nFolds - 1} · error = mean absolute error of the MODIS occupied-cell fraction`}
      className="harmonization-panel"
    >
      <div className="harmonization-methods">
        {METHOD_KEYS.map((key) => (
          <div key={key} className={`harmonization-method${key === "A_seasonal" ? " best" : ""}`}>
            <span><i style={{ background: METHOD_COLOR[key] }} aria-hidden="true" />{METHOD_LABEL[key]}</span>
            <strong>{formatPp(harmonization.mae[key])}</strong>
            <small>{harmonization.methods[key]}</small>
          </div>
        ))}
      </div>
      <div className="harmonization-scores">
        <span><strong>{harmonization.folds_A_better_than_C} of {nFolds}</strong> held-out years: monthly ratio beats the seasonal average</span>
        <span><strong>{harmonization.folds_A_better_than_B} of {nFolds}</strong> held-out years: monthly ratio beats a single ratio</span>
      </div>
      <ReactECharts aria-label="Prediction error by held-out year for each method" option={option} style={{ height: 230 }} opts={{ renderer: "canvas" }} />
      <div className="harmonization-decision">
        <Scale size={16} aria-hidden="true" />
        <div>
          <strong>Result: {harmonization.decision}</strong>
          <p>VIIRS carries real information about MODIS activity, but the gain over a single ratio is not consistent across years, so no merged series is published.</p>
          <p className="harmonization-conclusion">{harmonization.conclusion}</p>
        </div>
      </div>
    </Panel>
  );
}
