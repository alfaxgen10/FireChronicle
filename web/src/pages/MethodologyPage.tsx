import { ArrowUpRight, Check, Database, Download, FileJson2, FileSpreadsheet, Globe2, Info, ShieldAlert } from "lucide-react";
import { SENSOR_IDS, type FireChronicleData } from "../data/contracts";
import { AOI_LABEL, AOI_NOTE, DownloadButton, downloadJson, formatConfigName, IN_SAMPLE_NOTE, MODIS_RECORD_NOTE, PageHeader, Panel, RELIABILITY_NOTE, SCOPE_NOTE, SPEARMAN_NOTE, toCsv, TYPE_FIELD_NOTE } from "../ui/shared";

/** Release limitations from the Stage 6A scientific audit (docs/SCIENTIFIC_AUDIT.md §0). */
const RELEASE_LIMITATIONS = [
  SCOPE_NOTE,
  MODIS_RECORD_NOTE,
  TYPE_FIELD_NOTE,
  RELIABILITY_NOTE,
  SPEARMAN_NOTE,
  IN_SAMPLE_NOTE,
  "Per-configuration calendar classifications use the stored value consistently_elevated; for a single configuration this means only that the month exceeded its own threshold, not agreement across configurations. It is shown as \u201celevated (single configuration)\u201d.",
  `Study area: ${AOI_LABEL}. ${AOI_NOTE} The rectangle may include neighbouring areas and water; no land/water mask is applied.`,
  "Partial-cell weighting: the 18 southern boundary cells (0.25\u00b0) lie only 60% inside the box (80% for the 9 cells at 0.5\u00b0), yet each counts as one full cell in the denominator, so they are less likely to be occupied.",
];

export default function MethodologyPage({ data }: { data: FireChronicleData }) {
  const sources = data.methodology.data_sources;
  const modisSource = sources.find((source) => source.sensor === "MODIS_C61");
  const registry = data.reliability.config_registry_history;
  const maximumBaselineDepth = Math.max(
    0,
    ...SENSOR_IDS.flatMap((sensor) =>
      Array.from({ length: 12 }, (_, monthIndex) =>
        data.calendar.sensors[sensor].months.filter(
          (month) => month.month === monthIndex + 1 && month.occupied_cell_fraction != null,
        ).length,
      ),
    ),
  );
  const exportFiles = [
    ["regions.json", data.regions],
    ["calendar.json", data.calendar],
    ["sensors.json", data.sensors],
    ["reliability.json", data.reliability],
    ["methodology.json", data.methodology],
  ] as const;
  return (
    <>
      <PageHeader kicker="PROVENANCE / SCIENTIFIC RECORD" title="Methodology & export" description="Traceable product sources, spatial conventions, seasonal definitions, reliability configurations, and direct exports of the schema-validated frontend contracts." />
      <div className="provenance-cards">
        <div className="provenance-card"><span>CONTRACT</span><strong>{data.calendar.contract_version}</strong><small>JSON interface version</small></div>
        <div className="provenance-card"><span>PROCESSING</span><strong>{data.calendar.processing_version}</strong><small>Pipeline release identifier</small></div>
        <div className="provenance-card"><span>GENERATED UTC</span><strong>{new Date(data.calendar.generated_at).toLocaleDateString(undefined, { timeZone: "UTC" })}</strong><small>{new Date(data.calendar.generated_at).toLocaleTimeString(undefined, { timeZone: "UTC", timeZoneName: "short" })}</small></div>
        <div className="provenance-card"><span>RELIABILITY REGISTRY</span><strong>v{data.reliability.config_registry_version}</strong><small>{Object.keys(data.reliability.configurations).length} declared configurations</small></div>
      </div>
      <Panel title="Scientific provenance" subtitle="NASA FIRMS active-fire data products declared in the methodology export">
        <div className="source-list">
          {sources.map((source) => (
            <article key={source.sensor} className="source-card">
              <div className={`source-symbol ${source.sensor === "MODIS_C61" ? "modis" : "viirs"}`}><Globe2 size={17} aria-hidden="true" /></div>
              <div className="source-details"><span className="eyebrow">{source.sensor === "MODIS_C61" ? "MODIS · Terra / Aqua" : "VIIRS · NOAA-20 / J1"}</span><strong>{source.product}</strong><p>{source.provider} · {source.temporal_coverage} · {source.access_method}</p><small>{Object.entries(source.source_versions_by_type).map(([sourceType, versions]) => `${sourceType.toUpperCase()} versions: ${versions.join(", ") || "not reported"}`).join(" · ")}</small><small>{source.provenance_note}</small></div>
              <a className="source-link" href={source.url} target="_blank" rel="noreferrer">NASA FIRMS <ArrowUpRight size={14} aria-hidden="true" /></a>
            </article>
          ))}
        </div>
        <div className="citation-box"><Info size={15} aria-hidden="true" /><span>Data provenance is supplied by the exported manifest. This frontend does not contain NASA API credentials, fetch live detections, or imply that fixture values are genuine NASA observations.</span></div>
      </Panel>
      <div className="methodology-grid">
        <Panel title="Sensor differences" subtitle="Why the observation series are not interchangeable">
          <div className="sensor-method-grid">
            <div><span className="sensor-swatch modis" /><strong>MODIS · Terra / Aqua</strong><p>{modisSource?.product ?? "MODIS active-fire observations"}; nominal native pixel scale is approximately 1 km.</p>{modisSource?.product_versions.length ? <p>Source product-version IDs: {modisSource.product_versions.join(", ")}.</p> : null}</div>
            <div><span className="sensor-swatch viirs" /><strong>VIIRS · NOAA-20</strong><p>Collection 2 active-fire observations; nominal native pixel scale is approximately 375 m.</p></div>
          </div>
          <p className="method-note">Different spatial resolutions, overpass times, and detection sensitivities affect what each instrument observes. Common gridding does not equalize sensor response. Overlap ratios are descriptive statistics, not calibration factors.</p>
        </Panel>
        <Panel title="Activity index & grid conventions" subtitle="Primary grid: Convention B · sensitivity: Convention A">
          <div className="formula-block"><span>{data.methodology.index_definition.name}</span><code>{data.methodology.index_definition.formula}</code></div>
          <div className="grid-definition-list">
            <div><strong>Convention B · primary</strong><span>{data.methodology.geographic_support.metric_definitions.B ? data.methodology.geographic_support.primary_convention : "Every intersecting grid cell."}</span></div>
            <div><strong>Convention A · sensitivity</strong><span>{data.methodology.geographic_support.sensitivity_convention}</span></div>
          </div>
          <p className="method-note">{data.methodology.index_definition.interpretation_caveat}</p>
          <div className="resolution-chips">{data.methodology.geographic_support.cell_counts.map((item) => <span key={`${item.convention}-${item.resolution_deg}`}>Convention {item.convention} · {item.resolution_deg}° · {item.eligible_cells} cells</span>)}</div>
        </Panel>
      </div>
      <Panel title="Seasonal baseline & anomaly" subtitle="Reference period and classification method">
        <div className="baseline-overview">
          <div className="baseline-years"><small>DECLARED BASELINE</small><strong>{data.methodology.baseline_window.start}—{data.methodology.baseline_window.end}</strong><span>{data.methodology.baseline_window.note}</span></div>
          <div className="baseline-description"><strong>Same-month comparison</strong><p>Monthly anomaly is observed occupied-cell fraction minus the median for that calendar month. Elevated classification is based on the same calendar month’s threshold in the baseline years. Up to {maximumBaselineDepth} valid observation{maximumBaselineDepth === 1 ? "" : "s"} contribute to any monthly baseline in the loaded exports, so estimates are indicative, not a long-term climatology.</p></div>
        </div>
        <div className="processing-steps">{data.methodology.processing_steps.map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, "0")}</span><p>{step.replace(/^\d+\.\s*/, "")}</p></div>)}</div>
      </Panel>
      <Panel title="Reliability registry & change history" subtitle="Configuration declarations and version history are loaded directly from the data contract">
        <div className="registry-history">
          {Object.entries(registry).map(([version, names]) => (
            <div key={version} className={`registry-version${Number(version) === data.reliability.config_registry_version ? " current" : ""}`}>
              <div><span className="version-tag">REGISTRY {version}{Number(version) === data.reliability.config_registry_version && <Check size={13} aria-hidden="true" />}</span><strong>{names.length} configurations</strong></div>
              <p>{names.map((name) => formatConfigName(name)).join(" · ")}</p>
            </div>
          ))}
        </div>
        <div className="citation-box"><ShieldAlert size={15} aria-hidden="true" /><span>Agreement labels require at least {data.reliability.cross_sensor_rule.min_evaluable_configs} evaluable configurations including evidence from {data.reliability.cross_sensor_rule.required_sensors.map((id) => id === "MODIS_C61" ? "MODIS Terra / Aqua" : "VIIRS NOAA-20 / J1").join(" and ")}. Sensor-specific findings do not constitute cross-sensor agreement. Analytical stability is not a probability of correctness.</span></div>
      </Panel>
      <Panel title="Data limitations" subtitle="Important interpretation guardrails">
        <div className="limitations-list">
          {data.methodology.scientific_guardrails.map((item) => <div key={item}><span className="limitation-dot" /><p>{item}</p></div>)}
          {data.methodology.index_definition.limitations.map((item) => <div key={item}><span className="limitation-dot subdued" /><p>{item}</p></div>)}
          {RELEASE_LIMITATIONS.map((item) => <div key={item}><span className="limitation-dot" /><p>{item}</p></div>)}
        </div>
      </Panel>
      <Panel title="Export schema-validated data" subtitle="Download the same precomputed JSON contracts loaded by this application">
        <div className="export-toolbar">
          <div><Database size={16} aria-hidden="true" /><span>All files are schema-validated (checked against the data contract) before they are displayed or exported. Schema validation is not scientific validation.</span></div>
          <div className="export-actions">
            <DownloadButton onClick={() => toCsv("firechronicle-calendar.csv", SENSOR_IDS.flatMap((sensor) => data.calendar.sensors[sensor].months.map((month) => ({ sensor, ...month }))))}><FileSpreadsheet size={14} aria-hidden="true" />Calendar CSV</DownloadButton>
            <DownloadButton onClick={() => toCsv("firechronicle-reliability.csv", data.reliability.per_period)}><FileSpreadsheet size={14} aria-hidden="true" />Reliability CSV</DownloadButton>
          </div>
        </div>
        <div className="export-file-list">
          {exportFiles.map(([filename, file]) => (
            <div className="export-file" key={filename}>
              <div className="file-icon"><FileJson2 size={17} aria-hidden="true" /></div><div><strong>{filename}</strong><small>Contract {file.contract_version} · Processing {file.processing_version}</small></div>
              <button className="icon-button" aria-label={`Download ${filename}`} title={`Download ${filename}`} onClick={() => downloadJson(`firechronicle-${filename}`, file)}><Download size={16} aria-hidden="true" /></button>
            </div>
          ))}
        </div>
      </Panel>
      <div className="method-footer-note">Citation and product coverage should be re-verified against the specific FIRMS archive manifest before scientific publication.</div>
    </>
  );
}
