import type { ReactNode } from "react";
import { AlertTriangle, ArrowDownToLine, CircleHelp } from "lucide-react";
import type { FireChronicleData, SensorId } from "../data/contracts";
import { hasFixtureData, fixtureWarnings } from "../data/loadData";

export function FixtureNotice({ data }: { data: FireChronicleData }) {
  if (!hasFixtureData(data)) return null;
  const warnings = [...new Set(fixtureWarnings(data))];
  return (
    <section className="fixture-banner" role="alert" aria-label="Synthetic fixture data warning">
      <div className="fixture-icon"><AlertTriangle size={17} aria-hidden="true" /></div>
      <div>
        <strong>SYNTHETIC FIXTURE DATA — NOT NASA OBSERVATIONS</strong>
        <p>{warnings.length > 0 ? warnings.join(" · ") : "One or more loaded data exports are marked as synthetic fixtures."} All activity and comparison values shown are illustrative only.</p>
      </div>
    </section>
  );
}

export function PageHeader({ kicker, title, description, children }: {
  kicker: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{kicker}</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {children && <div className="heading-actions">{children}</div>}
    </div>
  );
}

export function Panel({ title, subtitle, action, children, className = "" }: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-heading">
        <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StatCard({ label, value, detail, icon, tone = "orange" }: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  tone?: "orange" | "teal" | "blue" | "neutral";
}) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}>{icon}</div>
      <div className="stat-copy"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
    </div>
  );
}

export function SensorSelector({ value, onChange, id = "sensor-select" }: {
  value: SensorId;
  onChange: (sensor: SensorId) => void;
  id?: string;
}) {
  return (
    <label className="field-control" htmlFor={id}>
      <span className="sr-only">Select satellite sensor</span>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value as SensorId)}>
        <option value="MODIS_C61">MODIS · Terra / Aqua</option>
        <option value="VIIRS_J1_C2">VIIRS · NOAA-20</option>
      </select>
    </label>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return <div className="empty-state"><CircleHelp size={18} aria-hidden="true" /><div><strong>{title}</strong><p>{children}</p></div></div>;
}

/** Conservative study-area name: the rectangle has not been checked against provincial boundaries. */
export const AOI_LABEL = "South Sumatra-region pilot AOI";
export const AOI_NOTE = "Rectangular bounding box; not verified against South Sumatra provincial boundaries.";

/** Plain-language meaning of the per-month classification, shared by every page. */
export const IN_SAMPLE_NOTE =
  "Classifications are descriptive and in-sample: each month is compared with the same calendar month across 2019–2024, including itself. " +
  "Elevated means a high within-month historical rank, not a validated prediction. No independent holdout validation has been performed.";

/** Scope statement used across the application. */
export const SCOPE_NOTE =
  "A sensor-aware historical fire-activity and reliability pilot: comparative, observation-aware analysis of MODIS and VIIRS kept as separate records. " +
  "Historical window 2019–2024 (FIRMS archive files); 2025 and January–October 2026 are compared afterwards, with Aug/Sep–Oct 2026 from near-real-time (NRT) files. " +
  "The sensors are not calibrated or fused into an equivalent series, and the record does not span 20+ years.";

/** Stage 6B audit finding P1-1 and P1-2 (MODIS record homogeneity). */
export const MODIS_RECORD_NOTE =
  "MODIS record changes over time. Observations from 2019–2022 are MODIS Collection 6 (version 6.03); from January 2023 they are Collection 6.1 (61.03; NRT 6.1NRT), " +
  "so the 2019–2024 baseline combines two product collections. The satellites' observation times also drift: the median daytime detection time moved from about 10:35 to 08:39 local time for Terra " +
  "and from about 13:41 to 15:43 for Aqua between 2019 and 2026 (audit measurement from retained detections, UTC+7). Fire activity varies through the day, so changing observation times can " +
  "change how much activity is detected. MODIS 2025–2026 comparisons with the 2019–2024 baseline should be interpreted with both limitations in mind. VIIRS (NOAA-20) does not share these two " +
  "issues, but it is a different sensor with its own limitations, not a ground truth or a replacement for MODIS.";

/** Stage 6B audit finding P1-3 (FIRMS archive `type` field). */
export const TYPE_FIELD_NOTE =
  "The pipeline does not filter the FIRMS archive `type` field, so retained detections can include sources the data flag as static land sources, offshore sources or volcanoes. " +
  "In the Stage 6B audit these were 3.1% of retained 2019–2024 VIIRS detections (0.4% for MODIS); excluding them would change a month's occupied-cell fraction by at most 2.8 percentage points (VIIRS) " +
  "and 1.4 percentage points (MODIS). NRT files have no `type` field.";

/** Stage 6B audit finding P2-1 (Spearman p-value). */
export const SPEARMAN_NOTE =
  "The exported Spearman correlation p-value (sensors.json) assumes independent observations. The 72 monthly values are autocorrelated and share a seasonal cycle, " +
  "so the p-value should not be read as though all 72 months were independent; it overstates the statistical precision.";

/** Stage 6B audit, reliability interpretation. */
export const RELIABILITY_NOTE =
  "Reliability labels show agreement across five tested configurations. The configurations share the same underlying observations and are not independent datasets. " +
  "Leave-one-year-out with the 75th-percentile threshold produces zero changes by construction (with six values both rules select the same top two years), so it is not independent robustness evidence. " +
  "With the 90th-percentile configuration it changes 3 of 72 classifications, none of which alters a reported stability label.";

/**
 * Display text for a single-configuration `anomaly_label` (calendar.json).
 * The stored value `consistently_elevated` is kept for contract compatibility, but for one
 * configuration it only means "above that month's threshold", not cross-configuration agreement.
 */
export function formatAnomalyLabel(label: string) {
  if (label === "consistently_elevated") return "elevated (single configuration)";
  return label.replaceAll("_", " ");
}

/** Display name for a reliability configuration key, keeping the official MODIS / VIIRS capitalization. */
export function formatConfigName(name: string) {
  return name
    .split("_")
    .map((word) => (/^(modis|viirs)$/i.test(word) ? word.toUpperCase() : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(" ");
}

export function formatPercent(value: number | null | undefined, digits = 2) {
  return value == null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined) {
  return value == null ? "—" : new Intl.NumberFormat("en-US").format(value);
}

export function monthName(month: number, short = false) {
  return new Intl.DateTimeFormat("en", { month: short ? "short" : "long", timeZone: "UTC" })
    .format(new Date(Date.UTC(2020, month - 1, 1)));
}

export function toCsv(filename: string, rows: Record<string, unknown>[]) {
  if (rows.length === 0) return;
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const escape = (value: unknown) => {
    const text = value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  };
  const csv = [columns.map(escape).join(","), ...rows.map((row) => columns.map((column) => escape(row[column])).join(","))].join("\r\n");
  downloadFile(filename, csv, "text/csv;charset=utf-8");
}

export function downloadJson(filename: string, data: unknown) {
  downloadFile(filename, JSON.stringify(data, null, 2), "application/json");
}

function downloadFile(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function DownloadButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return <button className="button button-secondary" onClick={onClick}><ArrowDownToLine size={15} aria-hidden="true" />{children}</button>;
}
