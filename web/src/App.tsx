import { lazy, Suspense, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CalendarDays,
  ChevronRight,
  Compass,
  Database,
  Flame,
  FlaskConical,
  Home,
  LoaderCircle,
  Satellite,
} from "lucide-react";
import { loadCellActivity, loadFireChronicleData, loadHarmonization, loadRecentActivity } from "./data/loadData";
import type { CellActivityData, FireChronicleData, HarmonizationData, RecentActivityData } from "./data/contracts";
const ExplorePage = lazy(() => import("./pages/ExplorePage"));
const CalendarPage = lazy(() => import("./pages/CalendarPage"));
const ReliabilityPage = lazy(() => import("./pages/ReliabilityPage"));
const MethodologyPage = lazy(() => import("./pages/MethodologyPage"));
const OverviewPage = lazy(() => import("./pages/OverviewPage"));
import { AOI_LABEL, AOI_NOTE, FixtureNotice } from "./ui/shared";

const navigation = [
  { to: "/", label: "Overview", icon: Home },
  { to: "/explore", label: "Explore", icon: Compass },
  { to: "/calendar", label: "Historical calendar", icon: CalendarDays },
  { to: "/reliability", label: "Reliability lab", icon: FlaskConical },
  { to: "/methodology", label: "Methodology & export", icon: Database },
];

export default function App() {
  const [data, setData] = useState<FireChronicleData | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [recent, setRecent] = useState<RecentActivityData | null>(null);
  const [harmonization, setHarmonization] = useState<HarmonizationData | null>(null);
  const [cellActivity, setCellActivity] = useState<CellActivityData | null>(null);

  useEffect(() => {
    let active = true;
    loadCellActivity().then((loaded) => {
      if (active) setCellActivity(loaded);
    });
    loadHarmonization().then((loaded) => {
      if (active) setHarmonization(loaded);
    });
    // Optional: the application works without it.
    loadRecentActivity().then((loaded) => {
      if (active) setRecent(loaded);
    });
    loadFireChronicleData()
      .then((loaded) => {
        if (active) setData(loaded);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason : new Error(String(reason)));
      });
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <main className="state-screen">
        <div className="state-card">
          <div className="state-icon error-icon"><AlertTriangle size={21} aria-hidden="true" /></div>
          <p className="eyebrow">Data integrity check</p>
          <h1>Research data unavailable</h1>
          <p className="muted">{error.message}</p>
          <p className="small muted">Check the five JSON files in <code>public/data/</code> and reload.</p>
          <button className="button button-secondary" onClick={() => window.location.reload()}>Retry data load</button>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="state-screen">
        <div className="loading-mark"><LoaderCircle size={22} className="spin" aria-hidden="true" /></div>
        <p className="eyebrow">Initializing observation archive</p>
        <p className="muted">Validating exported data contracts…</p>
      </main>
    );
  }

  const region = data.regions.regions[0];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="FireChronicle home">
          <span className="brand-mark"><Flame size={20} fill="currentColor" aria-hidden="true" /></span>
          <span><strong>FireChronicle</strong><small>SATELLITE FIRE INTELLIGENCE</small></span>
        </Link>
        <div className="nav-section-label">WORKSPACE</div>
        <nav className="main-nav" aria-label="Main navigation">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"} aria-label={label} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
              <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
              <span>{label}</span>
              {to === "/explore" && <ChevronRight className="nav-arrow" size={15} aria-hidden="true" />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="region-mini">
            <span className="live-dot" />
            <div title={region ? `${region.bbox.join(", ")} · ${AOI_NOTE}` : AOI_NOTE}><small>ACTIVE STUDY AREA</small><strong>{AOI_LABEL}</strong></div>
          </div>
          <div className="sidebar-foot"><span>ZERODAY_SQUAD · SPACE APPS 2026</span><span>v{data.calendar.processing_version}</span></div>
        </div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div className="mobile-brand"><span className="brand-mark"><Flame size={18} fill="currentColor" aria-hidden="true" /></span><strong>FireChronicle</strong></div>
          <div className="breadcrumbs"><span>{AOI_LABEL}</span><ChevronRight size={14} aria-hidden="true" /><span className="breadcrumb-current">Observation workspace</span></div>
          <div className="topbar-meta"><Satellite size={15} aria-hidden="true" /><span>MODIS + VIIRS</span><span className="meta-divider" /><span>2019—2024</span></div>
        </header>
        {data.regions.is_fixture || data.calendar.is_fixture || data.sensors.is_fixture || data.reliability.is_fixture || data.methodology.is_fixture
          ? <FixtureNotice data={data} />
          : null}
        <div className="page-content">
          <Suspense fallback={<div className="loading-inline"><LoaderCircle size={17} className="spin" /> Loading workspace module…</div>}>
            <Routes>
              <Route path="/" element={<OverviewPage data={data} recent={recent} harmonization={harmonization} cellActivity={cellActivity} />} />
              <Route path="/explore" element={<ExplorePage data={data} cellActivity={cellActivity} />} />
              <Route path="/calendar" element={<CalendarPage data={data} recent={recent} />} />
              <Route path="/reliability" element={<ReliabilityPage data={data} harmonization={harmonization} />} />
              <Route path="/methodology" element={<MethodologyPage data={data} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </div>
        <footer className="app-footer">
          <span><Activity size={14} aria-hidden="true" /> FIRECHRONICLE · REGIONAL OBSERVATION RECORD</span>
          <span>NASA FIRMS data products · {AOI_LABEL}, Indonesia</span>
        </footer>
      </main>
    </div>
  );
}
