import { ArrowRight, CalendarDays, Compass, Database, Flame, FlaskConical, Layers3, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import { SENSOR_IDS, type CellActivityData, type FireChronicleData, type HarmonizationData, type RecentActivityData, type SensorId } from "../data/contracts";
import FireMapSection from "../ui/FireMapSection";
import { formatPp } from "../ui/HarmonizationPanel";
import { AOI_LABEL, AOI_NOTE, formatNumber, formatPercent, MODIS_RECORD_NOTE, RELIABILITY_NOTE, SCOPE_NOTE, SPEARMAN_NOTE, TYPE_FIELD_NOTE } from "../ui/shared";

const destinations = [
  { to: "/explore", title: "Explore", description: "Study area and monthly observations for each sensor.", icon: Compass },
  { to: "/calendar", title: "Historical calendar", description: "Pick a month and compare it with its seasonal baseline.", icon: CalendarDays },
  { to: "/reliability", title: "Reliability lab", description: "MODIS vs VIIRS, harmonization test and stability labels.", icon: FlaskConical },
  { to: "/methodology", title: "Methodology & export", description: "Sources, processing steps and CSV/JSON downloads.", icon: Database },
];

/** Planned work from the FireChronicle blueprint that is not part of this prototype. */
const ROADMAP = [
  { title: "Detection-level layer", text: "Individual detections with confidence and day/night filters, alongside the current per-cell map." },
  { title: "Evidence-grounded AI assistant", text: "Questions answered only through read-only tools over the verified exports, with cited values." },
  { title: "Longer MODIS record", text: "Extending the baseline back to 2001, with the collection change handled explicitly." },
  { title: "More regions", text: "Additional study areas with verified administrative boundaries and a land/water mask." },
];

function mean(values: Array<number | null>) {
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  return valid.length > 0
    ? valid.reduce((total, value) => total + value, 0) / valid.length
    : null;
}

type PairedPoint = { period: string; modis: number; viirs: number };

const CHART = { width: 760, height: 280, left: 44, right: 12, top: 14, bottom: 30 };

function PairedSeriesChart({ points }: { points: PairedPoint[] }) {
  if (points.length < 2) return null;
  const plotW = CHART.width - CHART.left - CHART.right;
  const plotH = CHART.height - CHART.top - CHART.bottom;
  const maxValue = Math.max(...points.flatMap((p) => [p.modis, p.viirs]));
  const yMax = Math.max(0.1, Math.ceil(maxValue * 10) / 10);
  const x = (index: number) => CHART.left + (index / (points.length - 1)) * plotW;
  const y = (value: number) => CHART.top + plotH - (value / yMax) * plotH;
  const path = (key: "modis" | "viirs") =>
    points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const yTicks = [0, yMax / 2, yMax];
  const yearTicks = points
    .map((p, i) => ({ year: p.period.slice(0, 4), month: p.period.slice(5), i }))
    .filter((t) => t.month === "01");

  return (
    <svg
      className="overview-chart"
      viewBox={`0 0 ${CHART.width} ${CHART.height}`}
      role="img"
      aria-labelledby="overview-chart-title overview-chart-desc"
    >
      <title id="overview-chart-title">Monthly occupied-cell fraction by sensor</title>
      <desc id="overview-chart-desc">
        Line chart of the monthly occupied-cell fraction (share of eligible grid cells with at least one detection, 0 to {Math.round(yMax * 100)} percent) for MODIS and VIIRS, plotted as separate uncalibrated series, for the {points.length} months with quality-filtered detections from both sensors, {points[0].period} to {points[points.length - 1].period}. MODIS is drawn as a dashed line and VIIRS as a solid line.
      </desc>
      {yTicks.map((tick) => (
        <g key={tick}>
          <line x1={CHART.left} x2={CHART.width - CHART.right} y1={y(tick)} y2={y(tick)} className="overview-chart-grid" />
          <text x={CHART.left - 8} y={y(tick) + 3.5} textAnchor="end" className="overview-chart-label">{Math.round(tick * 100)}%</text>
        </g>
      ))}
      {yearTicks.map((tick) => (
        <text key={tick.year} x={x(tick.i)} y={CHART.height - 9} textAnchor="start" className="overview-chart-label">{tick.year}</text>
      ))}
      <path d={path("modis")} className="overview-chart-line modis" />
      <path d={path("viirs")} className="overview-chart-line viirs" />
    </svg>
  );
}

const SHORT: Record<SensorId, string> = { MODIS_C61: "MODIS", VIIRS_J1_C2: "VIIRS" };

export default function OverviewPage({ data, recent = null, harmonization = null, cellActivity = null }: {
  data: FireChronicleData;
  recent?: RecentActivityData | null;
  harmonization?: HarmonizationData | null;
  cellActivity?: CellActivityData | null;
}) {
  // Conservative name: the bounding box has not been verified against provincial boundaries.
  const regionName = AOI_LABEL;
  const baseline = data.calendar.baseline_window;
  const windowLabel = `${baseline.start}\u2013${baseline.end}`;
  const baselineYears = baseline.end - baseline.start + 1;

  const paired: PairedPoint[] = data.sensors.overlap_diagnostics.detail.flatMap((row) =>
    row.modis_ocf != null && row.viirs_ocf != null
      ? [{ period: row.period, modis: row.modis_ocf, viirs: row.viirs_ocf }]
      : [],
  );
  const modisMean = mean(paired.map((p) => p.modis));
  const viirsMean = mean(paired.map((p) => p.viirs));

  const periods = data.reliability.per_period;
  const classificationSensitive = periods.filter((p) => p.stability_label === "classification_sensitive").length;
  const consistentlyElevated = periods.filter((p) => p.stability_label === "consistently_elevated").length;
  const notElevated = periods.filter((p) => p.stability_label === "not_elevated").length;
  const grid = data.calendar.grid_resolution_deg;
  const harmonizationSupported = data.sensors.overlap_diagnostics.harmonization_supported === true;
  const eligibleCells = data.calendar.sensors.MODIS_C61.months.find((m) => m.has_data)?.total_eligible_cells;
  const detections = (sensor: SensorId) =>
    data.calendar.sensors[sensor].months.reduce((total, month) => total + month.detection_count, 0);

  const recentYear = recent?.periods.recent.year;
  const recentSummary = recent && recentYear != null
    ? SENSOR_IDS.map((sensor) => {
      const rows = recent.sensors[sensor].records.filter((r) => r.year === recentYear);
      return { sensor, elevated: rows.filter((r) => r.elevated === true).length, withData: rows.filter((r) => r.has_data).length };
    })
    : null;
  const nFolds = harmonization ? Object.keys(harmonization.mae_by_year).length : 0;

  return (
    <div className="overview-page">
      <section className="ov-head" aria-labelledby="overview-title">
        <div className="ov-head-main">
          <p className="ov-kicker">NASA Space Apps Challenge 2026 · Harmonization of MODIS and VIIRS Hot Spots <span className="ov-badge">Prototype</span></p>
          <h1 className="overview-title" id="overview-title">
            FireChronicle
            <span>Regional fire activity, observed by two satellite sensors.</span>
          </h1>
          <p className="ov-lede">
            Where are satellite fire detections appearing in the {regionName}? Explore MODIS and VIIRS observations
            from {windowLabel}, compared with 2025–2026, and see which findings hold up when the analysis changes.
          </p>
        </div>
        <div className="ov-head-side">
          <dl className="ov-hero-stats">
            <div><dt>Sensors</dt><dd>02</dd><span>MODIS / VIIRS</span></div>
            <div><dt>Baseline</dt><dd>{baselineYears} yr</dd><span>{windowLabel}</span></div>
            <div><dt>Region</dt><dd>01</dd><span>Pilot AOI · {grid}° grid</span></div>
          </dl>
          <div className="ov-actions">
            <Link className="button button-primary overview-cta" to="/explore">
              Explore the analysis <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link className="ov-secondary" to="/calendar">Historical calendar</Link>
          </div>
        </div>
      </section>

      {cellActivity ? <FireMapSection cellActivity={cellActivity} baselineStart={baseline.start} baselineEnd={baseline.end} /> : null}

      <div className="ov-kpis" aria-label="Key figures">
        <div className="ov-kpi modis"><span><Flame size={15} aria-hidden="true" /> MODIS detections</span><strong>{formatNumber(detections("MODIS_C61"))}</strong><small>Quality-filtered, {windowLabel} · detections, not individual fires</small></div>
        <div className="ov-kpi viirs"><span><Flame size={15} aria-hidden="true" /> VIIRS detections</span><strong>{formatNumber(detections("VIIRS_J1_C2"))}</strong><small>Quality-filtered, {windowLabel} · not comparable with MODIS counts</small></div>
        <div className="ov-kpi elevated"><span><Layers3 size={15} aria-hidden="true" /> Consistently elevated</span><strong>{consistentlyElevated} <em>of {periods.length} months</em></strong><small>Elevated in every tested configuration</small></div>
        <div className="ov-kpi accent"><span><Scale size={15} aria-hidden="true" /> Harmonization</span><strong>{harmonization ? "Evaluated" : "Not applied"}</strong><small>{harmonization ? `Not applied · ${nFolds} held-out years tested, sensors kept separate` : "Sensors kept separate"}</small></div>
      </div>

      <section className="ov-users" aria-labelledby="overview-users-title">
        <div className="ov-section-head">
          <h2 id="overview-users-title">Who this is for</h2>
          <p>A standard hotspot map shows where detections occurred. FireChronicle also tests whether a historical conclusion still holds when the satellite sensor or the analysis method changes.</p>
        </div>
        <ul className="ov-users-list">
          <li><strong>Fire and haze researchers</strong><span>When the fire season peaks, which years and months were unusual, and whether both satellites agree.</span></li>
          <li><strong>Regional land managers</strong><span>Which periods recur, and how much confidence each finding deserves before it informs planning.</span></li>
          <li><strong>Educators and students</strong><span>A transparent worked example of using two satellite records carefully, with every limitation shown.</span></li>
        </ul>
        <p className="ov-users-note">For retrospective understanding only: FireChronicle is not a fire detection, alert or forecasting system.</p>
      </section>

      <div className="ov-grid">
        <section className="ov-card ov-evidence" aria-labelledby="overview-evidence-title">
          <div className="ov-card-head">
            <h2 id="overview-evidence-title">What the production data show</h2>
            <Link to="/reliability">Compare sensors <ArrowRight size={14} aria-hidden="true" /></Link>
          </div>
          <figure className="overview-figure">
            <figcaption>
              <strong>Monthly occupied-cell fraction</strong>
              <span>Occupied-cell fraction: the share of the {eligibleCells} eligible {grid}&deg; grid cells that contain at least one quality-filtered detection in the month (low-confidence records are excluded). {paired[0]?.period} to {paired[paired.length - 1]?.period}.</span>
              <span>Each sensor is plotted separately. The series are not calibrated to each other and are not fire counts or burned area.</span>
              <span className="overview-legend">
                <span><svg className="overview-legend-line modis" width="28" height="8" viewBox="0 0 28 8" aria-hidden="true"><line x1="1" y1="4" x2="27" y2="4" /></svg> MODIS (dashed)</span>
                <span><svg className="overview-legend-line viirs" width="28" height="8" viewBox="0 0 28 8" aria-hidden="true"><line x1="1" y1="4" x2="27" y2="4" /></svg> VIIRS (solid)</span>
              </span>
            </figcaption>
            <PairedSeriesChart points={paired} />
          </figure>
        </section>

        <div className="ov-side">
          {harmonization ? (
            <section className="ov-card ov-harmonization" aria-labelledby="overview-harmonization-title">
              <div className="ov-card-head">
                <h2 id="overview-harmonization-title">Harmonization test</h2>
                <Link to="/reliability">Details <ArrowRight size={14} aria-hidden="true" /></Link>
              </div>
              <p className="ov-card-text">Can VIIRS predict MODIS? Each year {harmonization.definition.years[0]}–{harmonization.definition.years[harmonization.definition.years.length - 1]} was held out and predicted from the others.</p>
              <dl className="ov-mini-stats">
                <div><dt>Monthly ratio</dt><dd>{formatPp(harmonization.mae.A_seasonal)}</dd></div>
                <div><dt>Single ratio</dt><dd>{formatPp(harmonization.mae.B_global)}</dd></div>
                <div><dt>No VIIRS</dt><dd>{formatPp(harmonization.mae.C_climatology)}</dd></div>
              </dl>
              <p className="ov-card-note">Mean error. Monthly ratio wins {harmonization.folds_A_better_than_C}/{nFolds} years against no VIIRS but only {harmonization.folds_A_better_than_B}/{nFolds} against a single ratio, so the sensors stay separate.</p>
            </section>
          ) : null}
          {recentSummary ? (
            <section className="ov-card" aria-labelledby="overview-recent-title">
              <div className="ov-card-head">
                <h2 id="overview-recent-title">{recentYear} against the {windowLabel} reference</h2>
                <Link to="/calendar">Calendar <ArrowRight size={14} aria-hidden="true" /></Link>
              </div>
              <dl className="ov-mini-stats two">
                {recentSummary.map(({ sensor, elevated, withData }) => (
                  <div key={sensor}><dt>{SHORT[sensor]}</dt><dd>{elevated} <small>of {withData} months elevated</small></dd></div>
                ))}
              </dl>
              <p className="ov-card-note">Each sensor against its own frozen thresholds. Nov–Dec {recentYear} not yet available.</p>
            </section>
          ) : null}
        </div>
      </div>

      <section className="ov-findings" aria-label="Key findings">
        <article className="overview-finding">
          <strong className="overview-finding-value">{formatNumber(paired.length)} months</strong>
          <h3>With detections from both sensors</h3>
          <p>Every month from {paired[0]?.period ?? "n/a"} to {paired[paired.length - 1]?.period ?? "n/a"} has quality-filtered detections from both MODIS and VIIRS. A month without detections would not establish zero fire activity.</p>
        </article>
        <article className="overview-finding">
          <strong className="overview-finding-value">{formatPercent(modisMean, 1)} <span>vs</span> {formatPercent(viirsMean, 1)}</strong>
          <h3>Mean occupied-cell fraction</h3>
          <p>MODIS and VIIRS, across the {formatNumber(paired.length)} months with detections from both sensors. Separate sensor summaries, not equivalent fire counts or a calibration factor.</p>
        </article>
        <article className="overview-finding">
          <strong className="overview-finding-value">{classificationSensitive} <span>of</span> {formatNumber(periods.length)}</strong>
          <h3>Classification-sensitive months</h3>
          <p>{consistentlyElevated} consistently elevated and {notElevated} not elevated. Stability measures sensitivity to configuration, not correctness. These are descriptive, in-sample classifications of {windowLabel} without independent holdout validation.</p>
        </article>
      </section>

      <section className="ov-journey" aria-labelledby="overview-navigation-title">
        <div className="ov-section-head">
          <h2 id="overview-navigation-title">The observation workspace</h2>
          <p>Follow the analysis from observations to evidence.</p>
        </div>
        <ul className="ov-journey-list">
          {destinations.map(({ to, title, description, icon: Icon }, index) => (
            <li key={to}>
              <Link to={to}>
                <span className="ov-step">{String(index + 1).padStart(2, "0")}</span>
                <Icon size={18} aria-hidden="true" />
                <strong>{title}</strong>
                <small>{description}</small>
                <ArrowRight className="ov-journey-arrow" size={15} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="ov-roadmap" aria-labelledby="overview-roadmap-title">
        <div className="ov-section-head">
          <h2 id="overview-roadmap-title">Prototype scope</h2>
          <p>Built for the hackathon: real FIRMS data, per-cell detection maps, sensor-specific calendar, harmonization test, reliability labels and exports. Planned next, not in this prototype:</p>
        </div>
        <ul className="ov-roadmap-list">
          {ROADMAP.map((item) => (
            <li key={item.title}><span className="ov-planned">Planned</span><strong>{item.title}</strong><small>{item.text}</small></li>
          ))}
        </ul>
      </section>

      <section className="overview-limits" aria-labelledby="overview-limits-title">
        <details>
          <summary>
            <h2 id="overview-limits-title">Scientific limitations</h2>
            <span>Detections are not fire counts or burned area · MODIS and VIIRS stay separate · classifications are in-sample. Show all</span>
          </summary>
          <ul>
            <li>Hotspot detections are not counts of individual fires, fire perimeters, or burned area.</li>
            <li>Occupied-cell fraction is an unweighted grid index, not an area estimate.</li>
            <li>{harmonizationSupported
              ? "The data export flags harmonization as supported, but this page applies none: MODIS and VIIRS series remain separate and uncalibrated. See the methodology for the validation basis."
              : "Cross-sensor harmonization has not been scientifically established or applied; MODIS and VIIRS series remain separate."}</li>
            <li>Reliability classifications measure sensitivity to analysis configurations, not the probability that a result is correct.</li>
            <li>Classifications are descriptive and in-sample ({windowLabel}): elevated means a high rank among the same calendar month across these years, including the month itself, not a validated prediction. No independent holdout validation has been performed.</li>
            <li>The study area is a rectangular pilot AOI around South Sumatra; it has not been verified against provincial boundaries and has no land/water mask. {AOI_NOTE}</li>
            <li>The southern row of boundary cells lies only partly inside the box but counts as full cells, slightly lowering their chance of being occupied.</li>
            <li>{SCOPE_NOTE}</li>
            <li>{MODIS_RECORD_NOTE}</li>
            <li>{TYPE_FIELD_NOTE}</li>
            <li>{RELIABILITY_NOTE}</li>
            <li>{SPEARMAN_NOTE}</li>
          </ul>
        </details>
      </section>
    </div>
  );
}
