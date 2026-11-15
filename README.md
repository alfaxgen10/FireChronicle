# FireChronicle

**NASA Space Apps Challenge 2026 — Harmonization of MODIS and VIIRS Hot Spots**  
Study area: South Sumatra-region pilot AOI, Indonesia (rectangular bounding box, not verified against provincial boundaries) | Time window: 2019–2024 (six-year pilot)

---

## What this is

FireChronicle is a sensor-aware historical fire-activity and reliability pilot: a comparative, observation-aware analysis of MODIS and VIIRS active-fire detections, kept as separate records, for one regional pilot AOI.  
It ingests official NASA FIRMS active-fire detections, processes them through a sensor-aware pipeline, and produces schema-validated JSON data for a React web application. (Schema validation checks the data contract; it is not scientific validation.)

**Scope of this release:** the supported historical window is **2019–2024** (six years, FIRMS archive files only). 2025 (archive) and January–October 2026 are compared afterwards with that frozen reference; August/September–October 2026 come from near-real-time (NRT) files (VIIRS Aug–Oct, MODIS Sep–Oct), which are processed differently from the archive. MODIS and VIIRS are **not** calibrated to each other or fused into an equivalent series. The challenge objective of a continuous, harmonized record spanning 20 or more years has **not** been achieved by this release. Extending the window requires new data, a new baseline decision and re-validation (see `docs/DATA_DOWNLOAD.md` and `docs/SCIENTIFIC_AUDIT.md` §5).

**Scientific guardrails (non-negotiable):**
- Hotspot detections are thermal-anomaly observations — not unique fires, burned area, severity, or ignition causes.
- MODIS and VIIRS records are not directly interchangeable; they are always kept separate.
- Missing months are labelled `null`, never fabricated zero.
- Reliability labels measure classification stability, not calibrated probability of truth.

**Known limitations** (also recorded in `methodology.json` and `docs/SCIENTIFIC_AUDIT.md` §5):
- Seasonal baselines use at most 6 observations per calendar month, so quantile thresholds are highly uncertain; months with fewer than `MIN_BASELINE_MONTHS = 3` observations receive `insufficient_evidence`.
- The 2019–2024 period cannot be claimed as long-term climatology. Results are indicative, not definitive.
- Common gridding does not equalise sensor sensitivity. No harmonization (calibration or fusion) is applied; any future harmonization would need independent validation.
- `occupied_cell_fraction` counts grid cells; it is not area-weighted and is not a burned-area, fire-count or severity measurement.
- **Classifications are descriptive and in-sample.** Each month is compared with the same calendar month across 2019–2024, including itself. "Elevated" means a high within-month historical rank (above that month's 75th or 90th percentile across the six years), not a validated prediction. **No independent holdout validation** (temporal, spatial or against reference fire data) has been performed.
- **Study area.** The bounding box `(101.5, -4.9, 106.0, -1.0)` is a rectangular pilot AOI around South Sumatra. It has not been verified against official provincial boundaries, may include neighbouring areas and water, and has no land/water mask.
- **Partial-cell weighting.** The 18 southern boundary cells at 0.25° lie only 60% inside the box (9 cells, 80%, at 0.5°) but each counts as one full cell in the denominator, so they are less likely to be occupied.

**Stage 6B audit disclosures** (details and measurements: `STAGE_6B_SCIENTIFIC_AUDIT.md`; disclosure locations: `STAGE_6B1_DISCLOSURE_REPORT.md`):
- **MODIS product-collection change.** MODIS observations from 2019–2022 are Collection 6 (version `6.03`); from January 2023 they are Collection 6.1 (`61.03`; NRT `6.1NRT`). The 2019–2024 MODIS baseline therefore combines two product collections, and MODIS 2025–2026 comparisons against it should be interpreted with this limitation.
- **Terra/Aqua observation-time drift.** The median daytime detection time (audit measurement from retained detections, local time UTC+7) moved from about 10:35 to 08:39 for Terra and from about 13:41 to 15:43 for Aqua between 2019 and 2026. Fire activity varies through the day, so changing observation times can change how much activity is detected; recent MODIS comparisons are qualified accordingly. VIIRS (NOAA-20) uses one product version and a stable observation time (median daytime detection about 13:30–13:45 local in every year), but it is a different sensor, not a ground truth or equivalent replacement for MODIS.
- **FIRMS `type` field not filtered.** Retained detections can include sources flagged by FIRMS as static land sources, offshore sources or volcanoes. Audit result: these were 3.1% of retained 2019–2024 VIIRS detections (0.4% for MODIS); excluding them would change a month's occupied-cell fraction by at most 2.8 percentage points (VIIRS; 1.4 for MODIS) and would change one primary MODIS elevated label (2024-12) and no primary VIIRS label. No filtering is applied in this release; NRT files have no `type` field.
- **Spearman p-value.** The exported `spearman_p` in `sensors.json` assumes independent observations. The 72 monthly values are temporally autocorrelated and share a seasonal cycle, so the p-value must not be interpreted as though all 72 months were independent; it overstates precision. The statistic is reported unchanged.
- **Reliability.** Labels show agreement across five tested configurations that share the same underlying observations; they are not independent datasets. Leave-one-year-out at q = 0.75 produces zero changes by construction and is not independent robustness evidence; at q = 0.90 it changes 3 of 72 classifications (2020-02, 2020-04, 2023-09), none of which alters a reported stability label.

---

## Repository structure

```
FireChronicle/
├── pipeline/           # Python scientific backend
│   ├── config.py       # All constants, bounding boxes, processing parameters
│   ├── ingest.py       # Raw NASA FIRMS CSV loading + provenance manifest
│   ├── validate.py     # Schema, coordinate, timestamp, quality validation
│   ├── normalize.py    # Type casting, UTC datetime, exclusion counting
│   ├── aggregate.py    # Monthly grid-cell aggregation (occupied-cell fraction)
│   ├── baseline.py     # Seasonal medians, anomaly calculation
│   ├── reliability.py  # Sensitivity analysis across predefined configurations
│   └── export.py       # Versioned JSON output for the React frontend
├── tests/              # pytest unit tests (synthetic fixtures only)
├── scripts/
│   └── run_pipeline.py # Full pipeline runner
├── data/
│   ├── raw/            # NASA FIRMS CSVs (gitignored — download separately)
│   │   ├── modis/
│   │   └── viirs/
│   ├── fixtures/       # SYNTHETIC test data — never used in real outputs
│   ├── processed/      # Parquet/DuckDB outputs (gitignored)
│   └── manifests/      # Per-file provenance records (repository-relative paths)
├── web/
│   ├── public/data/    # Versioned JSON contracts consumed by the frontend
│   │   ├── regions.json
│   │   ├── calendar.json
│   │   ├── sensors.json
│   │   ├── reliability.json
│   │   └── methodology.json
│   ├── src/            # React application (GitHub Copilot Agent responsibility)
│   ├── package.json    # Node scripts and dependency ranges
│   ├── package-lock.json
│   └── vercel.json     # Static hosting rewrites
├── docs/
│   ├── DATA_DOWNLOAD.md
│   └── SCIENTIFIC_AUDIT.md
├── requirements.txt        # Bounded Python dependency ranges
├── requirements-lock.txt   # Exact environment that reproduces the released JSON
└── README.md
```

---

## Tested environment

| Tool | Version tested |
|------|----------------|
| Python | 3.13.15 (Windows x64) |
| Node.js | 22.23.2 (`web/package.json` requires `>=22.12.0 <23`) |
| npm | 10.9.8 (lockfile version 3) |

---

## Clean-checkout setup

No NASA data, API keys or environment variables are needed to install, test or build. All commands run from the repository root unless noted.

**Python pipeline and tests**

```bash
python -m venv .venv
# Windows PowerShell:  .\.venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate
python -m pip install -r requirements.txt        # or requirements-lock.txt (Windows x64, Python 3.13 only)
python -m pytest tests/ -v
```

**Frontend**

```bash
cd web
npm ci              # installs exactly what package-lock.json records
npm test            # vitest
npm run build       # type-check, then production build into web/dist/
npm run preview     # serve the production build locally
```

`npm run dev` starts the development server instead. `web/dist/` is a build output and is not committed; Vercel builds it from `web/` (see `web/README.md`).

**Pipeline runs (optional)**

```bash
# Synthetic fixture data (outputs are labelled is_fixture: true and are not scientific results)
python scripts/run_pipeline.py --fixture

# Real NASA data (requires the raw FIRMS files; see below)
python scripts/run_pipeline.py
```

Running the pipeline rewrites `web/public/data/*.json` and `data/manifests/*.json`.

---

## Obtaining NASA FIRMS data

**Raw NASA FIRMS source datasets are not included in this repository.** They are excluded by `.gitignore` and must be obtained separately from NASA FIRMS. The released JSON contracts were generated from FIRMS download requests 849850 (MODIS, `M-C61`) and 849851 (VIIRS NOAA-20, `J1V-C2`); `data/manifests/` records each source file's name, repository-relative path, SHA-256 hash, row counts and product versions, so a fresh download can be checked against the files used.

See **[docs/DATA_DOWNLOAD.md](docs/DATA_DOWNLOAD.md)** for step-by-step instructions.

Place files in:
- `data/raw/modis/` — MODIS FIRMS active-fire CSVs; product-version IDs are recorded in the source manifest
- `data/raw/viirs/` — VIIRS NOAA-20 Collection 2 CSVs

---

## Frontend JSON contracts

Five JSON files in `web/public/data/` form the contract between the Python pipeline and the React frontend.  
All files include `contract_version`, `processing_version`, `generated_at`, and provenance fields.  
Schema details are embedded in each file under `methodology.json`.

| File | Contents |
|------|---------|
| `regions.json` | Region geometry, bounding box, supported sensors and years |
| `calendar.json` | Monthly activity per sensor: detection count, occupied-cell fraction, anomaly label |
| `sensors.json` | Side-by-side MODIS/VIIRS comparison and overlap diagnostics |
| `reliability.json` | Stability label per period across all sensitivity configurations |
| `methodology.json` | Processing steps, index definition, limitations, baseline window |

**Contract version: 1.2.0** (processing version 0.3.0) — additive over 1.0.0; see `docs/SCIENTIFIC_AUDIT.md` §12–13. Changes to these schemas must be reported explicitly.

Three optional files add to the five contracts without changing them. The application works if any of them is missing.

| File | Contents | Built by |
|------|---------|---------|
| `recent_activity.json` | 2025 and January–October 2026 compared with the frozen 2019–2024 reference | `scripts/build_recent_activity.py` |
| `harmonization.json` | Leave-one-year-out test of predicting MODIS from VIIRS (copied unchanged from `diagnostics/stage6e/results/results.json`) | `scripts/build_harmonization_json.py` |
| `cell_activity.json` | Quality-filtered detection counts per 0.25° cell, month and sensor, for the maps (no point coordinates) | `scripts/build_cell_activity.py` |

`build_cell_activity.py` stops unless the per-cell counts reproduce `detection_count` and `occupied_cells` for all 94 months (2019-01 to 2026-10) of both sensors in the released exports.

## Harmonization evaluation (Stage 6E)

Each year 2019–2024 was held out in turn and its MODIS occupied-cell fraction predicted from VIIRS using the other five years. Mean absolute error: monthly MODIS/VIIRS ratio 6.6 percentage points, single ratio 7.3, no VIIRS information (seasonal average) 9.7. The monthly ratio beat the seasonal average in 6 of 6 held-out years but beat the single ratio in only 3 of 6, so MODIS and VIIRS are kept as separate records and no harmonized series is produced.

The experiment evaluates a seasonal predictive relationship between VIIRS and MODIS occupied-cell fractions. Improved prediction does not establish sensor equivalence, measurement calibration, validated fusion or sensor-independent fire activity.

---

## Historical-to-recent activity (2025 holdout, 2026 recent)

`web/public/data/recent_activity.json` is an optional sixth file, shown on the Historical calendar page. It compares each 2025 and January–October 2026 month with the **frozen** 2019–2024 reference of the same sensor (primary configuration only: Convention B, 0.25°, q = 0.75). The five existing contracts are unchanged.

- Medians and thresholds are read from the released `calendar.json` and never recomputed with 2025 or 2026 data (`pipeline/recent_activity.py`; `compute_anomalies` is not used because its threshold would include every row passed to it).
- "Elevated" means the occupied-cell fraction exceeded the frozen 75th percentile of six historical values. `historical_rank` (1–7) ranks the month among those six values plus itself: 1 + the number of historical values that are higher, so 1 means no historical year was higher. Values are compared at the 6 decimals published in the JSON; equal values (the same number of occupied cells) tie and share the higher rank (`n_historical_values_tied`). This is a descriptive comparison, not a statistical test or validated prediction, and does not show that fires, burned area or damage increased.
- MODIS and VIIRS are never pooled. Archive and NRT months are labelled (`source_type`); NRT data are less comparable with the archive-based reference. November–December 2026 are `null` (not in the downloaded files), not zero.
- Rebuild with the raw FIRMS files (not distributed): `python scripts/build_recent_activity.py --raw-dir <path to data/raw>`. The build checks file SHA-256 values against `data/manifests/`, archive/NRT overlap and contiguity, and that re-aggregating 2019–2024 reproduces `calendar.json`; it does not rewrite manifests.

Current results (elevated months, each sensor against its own reference): MODIS 2025 Feb, Jun, Jul (3/12); VIIRS 2025 May, Jun (2/12); MODIS 2026 Jan, Feb, Mar, May–Oct (9/10); VIIRS 2026 Jan, Mar, Jun–Oct (7/10). Elevated in both sensors: 2025 Jun; 2026 Jan, Mar, Jun, Jul, Aug, Sep, Oct.

**Qualification of the MODIS results.** The MODIS 2025–2026 months are Collection 6.1 data observed at drifted Terra/Aqua times, compared with a 2019–2024 baseline that is part Collection 6 and was observed later in the day by Terra and earlier in the day by Aqua than in 2025–2026. Part of any MODIS difference may therefore come from the record itself rather than from fire activity. Both sensors' results also include FIRMS-flagged static, offshore and volcano sources (see "Stage 6B audit disclosures" above).

---

## Activity index

```
occupied_cell_fraction = eligible_cells_with_>=1_detection / total_eligible_cells
```

- **Primary grid (Convention B):** every grid cell intersecting the bounding box; all in-bounds detections are included. 0.25°: 288 cells (270 fully interior, 18 partial boundary cells). 0.5°: 72 cells (63 + 9).
- **Sensitivity grid (Convention A):** cells whose origin lies inside the box (270 / 63 cells). Exported alongside as `occupied_cell_fraction_convention_a`.
- Calculated separately per sensor before any comparison. Resolutions: 0.25° primary, 0.5° sensitivity.
- A ratio of cell counts: not area-weighted, not burned area, not a fire count.
- `null` = no detections after quality filtering, not confirmed zero activity.

---

## Reliability labels

| Label | Meaning |
|-------|---------|
| `consistently_elevated` | >= 2 evaluable configs incl. >= 1 MODIS and >= 1 VIIRS; all elevated |
| `not_elevated` | Same requirement; all not elevated |
| `classification_sensitive` | Same requirement; evaluable configs disagree |
| `insufficient_cross_sensor_evidence` | >= 2 evaluable configs, but MODIS or VIIRS has none |
| `insufficient_evidence` | Fewer than 2 evaluable configurations |

These labels describe agreement among in-sample classifications of 2019–2024; they measure stability, not correctness, and have not been validated on held-out data.

**Label naming note.** In `calendar.json`, the per-configuration `anomaly_label` uses the stored value `consistently_elevated` when a single configuration's month exceeds its threshold. For one configuration this only means "elevated in that configuration". The value is kept for JSON-contract compatibility; the web app displays it as "elevated (single configuration)". The cross-sensor `stability_label` in `reliability.json` is the only label that expresses agreement.

Five predefined configurations (registry v2): `primary`, `modis_coarse_grid`, `modis_strict_threshold` (MODIS) and `viirs_primary_grid`, `viirs_coarse_grid` (VIIRS). Single-sensor findings are kept per period in `sensor_specific` (`elevated` / `not_elevated` / `mixed` / `insufficient_evidence`); they are not cross-sensor agreement. Insufficient or missing configurations never count as agreement. Configurations are fixed in `pipeline/config.py` before analysis begins.

---

## Test results

```
Python (pytest):     335 passed (tests/ and diagnostics/stage6e/)
Frontend (vitest):   41 passed (7 files)
```

The Python suite covers schema validation, MODIS integer and VIIRS string confidence, normalization exclusions, grid geometry for both conventions (all four box edges, corners, exhaustive cell intersection), missing-data semantics, seasonal baselines and leave-one-year-out, the cross-sensor reliability rule (all 243 result combinations across the five configurations), overlap diagnostics, JSON contract checks, fixture schema checks, and manifest path portability and resolver safety. All test data are synthetic.

---

## Dependencies

`requirements.txt` uses bounded ranges: the original lower bounds, with upper bounds at the next untested major version. `requirements-lock.txt` pins every package exactly.

| Install from | Benefit | Cost |
|--------------|---------|------|
| `requirements.txt` | Receives compatible bug and security fixes | Results can differ in the last floating-point digits between versions |
| `requirements-lock.txt` | Reproduces the released JSON exactly | No automatic fixes; tested only on Windows x64 with Python 3.13 |

**Platform limitation:** `requirements-lock.txt` has been tested **only on Windows x64 with Python 3.13** (3.13.15). It has not been tested on Linux, macOS, ARM or other Python versions. Some pinned versions may lack wheels there, and exact output reproduction is unverified. On other platforms, install `requirements.txt`.

Both have been tested. With the lock file, re-running the pipeline on the same FIRMS files reproduces all five contracts exactly (ignoring `generated_at`). A fresh resolve of `requirements.txt` (pandas 3.1, numpy 2.5, scipy 1.18) passes all tests and reproduces every value except `sensors.json` → `overlap_diagnostics.spearman_p`, which differs at a relative 4 × 10⁻¹⁵.

Only pandas, numpy and scipy are imported by the pipeline. `pyarrow`, `geopandas`, `shapely`, `pyproj`, `duckdb`, `httpx`, `pydantic` and `pymupdf` are declared but not currently imported. PyMuPDF 2.x additionally installs `onnxruntime`, `networkx`, `pymupdf4llm` and `pymupdf-layout`, a large download; PyMuPDF 1.26.x (used in the lock file) does not.

The frontend uses `npm ci`, which installs exactly the versions in `web/package-lock.json` and fails if it disagrees with `package.json`.

---

## Data sources

- NASA FIRMS: https://firms.modaps.eosdis.nasa.gov/
- NASA Earthdata: https://www.earthdata.nasa.gov/data/tools/firms
- Challenge: https://www.spaceappschallenge.org/2026/challenges/modis-and-viirs-hot-spots/
- Map tiles: © OpenStreetMap contributors (https://www.openstreetmap.org/copyright)

**Acknowledgement.** We acknowledge the use of data from NASA's Fire Information for Resource Management System (FIRMS) (https://www.earthdata.nasa.gov/data/tools/firms), part of NASA's Earth Science Data and Information System (ESDIS).

---

## Use of AI (Super Intelligence) tools

AI coding assistants were used to develop this project, under the team's direction and review:

- **Kiro** (AI coding assistant): Python pipeline, tests, scripts, diagnostics, documentation and parts of the React frontend, including the Overview page, maps and harmonization panel.
- **GitHub Copilot Agent**: React frontend.
- **ChatGPT**: project planning documents (engineering blueprint, mentor proposal), proposal text and interface design suggestions.

All scientific results are computed by the code in `pipeline/`, `scripts/` and `diagnostics/` from NASA FIRMS files. No measurement, threshold or result was generated by an AI model. AI-written text in this README, the application and `docs/` was reviewed by the team. The application contains no AI-generated images.

---

## License

Code: MIT License (see `LICENSE`). NASA FIRMS data are provided by NASA; the derived JSON files in `web/public/data/` are distributed with the acknowledgement above.

## Team

ZeroDay_Squad, NASA Space Apps Challenge 2026.

---

## Ownership

| Layer | Owner |
|-------|-------|
| Python pipeline (`pipeline/`, `tests/`, `scripts/`) | Kiro Pro |
| React frontend (`web/src/`) | GitHub Copilot Agent |
| JSON contracts (`web/public/data/`) | Shared — schema changes must be coordinated |
