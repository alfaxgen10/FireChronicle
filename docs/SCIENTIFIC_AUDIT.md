# FireChronicle — Scientific and Engineering Audit

**Current version:** processing 0.3.0, contract 1.2.0 (release candidate)  
**Current test result:** Python 325 passed (pytest); frontend 26 passed (vitest, 4 files)

Section 0 describes the current state. Sections 1–13 are the chronological audit record (Phase 2 onward). Where a later decision replaced an earlier one, the earlier text is kept and marked **Superseded** or **Historical**.

---

## 0. Current status (release candidate)

**Data.** The released JSON contracts (`is_fixture: false`) were generated from real NASA FIRMS downloads: request 849850 (MODIS, `M-C61`, archive versions `6.03`/`61.03`, NRT `6.1NRT`) and request 849851 (VIIRS NOAA-20, `J1V-C2`, archive `2`, NRT `2.0NRT`). Per-file names, repository-relative paths, SHA-256 hashes and row counts are in `data/manifests/`. The raw CSV files are **not** included in the public release; see §6 and `docs/DATA_DOWNLOAD.md`.

**Scope.** Six-year pilot (2019–2024), one rectangular pilot AOI in the South Sumatra region. The challenge objective of a 20+ year harmonized record has not been achieved.

**Primary metric.** `occupied_cell_fraction` on **Convention B** (every grid cell intersecting the bounding box; 288 cells at 0.25°, 72 at 0.5°), approved in §12.1 and set in `pipeline/config.py` (`GRID_CONVENTION_PRIMARY = "B"`). Convention A (270 / 63 cells) is exported only as a sensitivity value (`occupied_cell_fraction_convention_a`).

**Reliability.** Registry v2, five configurations (3 MODIS, 2 VIIRS), cross-sensor rule of §12.2 (≥ 2 evaluable configurations including ≥ 1 MODIS and ≥ 1 VIIRS).

**Sensor comparability.** MODIS and VIIRS observations are **not interchangeable**:
- MODIS (~1 km) and VIIRS (~375 m) have different native pixel resolutions; VIIRS detects more small fires at the same grid resolution.
- Terra, Aqua (MODIS) and NOAA-20 (VIIRS) have different overpass times, so each sensor observes a different part of the diurnal fire cycle.
- Confidence is filtered with sensor-specific rules (§2.1, §6): MODIS integer confidence ≥ 30; VIIRS string confidence `nominal`/`high` (or `n`/`h`). The thresholds are not equivalent across sensors.
- Every metric is computed separately per sensor; detections and counts are never pooled. Common gridding reduces duplicate detections but does **not** make the sensors equivalent or equalise their sensitivity.
- `harmonization_supported` is `false`: no cross-sensor calibration is applied, and `ratio_viirs_to_modis` is an observation-level statistic, not a calibration factor. The 2019–2024 overlap is too short to separate sensor differences from interannual variability.

These statements match `sensors.json` → `overlap_diagnostics.limitations` and `methodology.json` → `scientific_guardrails`.

**Other limitations still in force.** Short-baseline limitations (§5); missing months are `null`, not confirmed zero; `occupied_cell_fraction` is a ratio of cell counts, not area-weighted, burned area, fire count or severity; reliability labels measure classification stability, not probability of truth.

**Classification status (Stage 6A audit).** All anomaly and reliability classifications are **descriptive and in-sample**. Thresholds are the per-calendar-month 0.75 / 0.90 quantiles of the same 2019–2024 values being classified, including the target month (`baseline.compute_anomalies`). "Elevated" therefore means a high within-month historical rank: with six values per month, at most two (q = 0.75) or one (q = 0.90) month per calendar month can be elevated per configuration. It is not a validated prediction. **No independent validation exists:** leave-one-year-out (below) re-uses the same six years, the 2025–2026 comparison (below) is a forward comparison of the primary configuration only, there is no spatial holdout, and there is no comparison with independent fire reference data. The 6 `consistently_elevated`, 26 `classification_sensitive` and 40 `not_elevated` values count monthly periods, not grid cells, and describe stability across configurations, not correctness.

**Label naming.** The per-configuration `anomaly_label` in `calendar.json` reuses the value `consistently_elevated` for a single configuration's above-threshold month. It is kept unchanged for contract compatibility; the web app displays it as "elevated (single configuration)". Only `reliability.json` → `stability_label` expresses cross-configuration agreement.

**Study area.** The bounding box `(101.5, -4.9, 106.0, -1.0)` is described as the **South Sumatra-region pilot AOI**. Its source ("Engineering Blueprint §3.1") is not in the repository, and "confirmed against FIRMS AOI" only shows that the download used the same box. It has not been checked against official provincial boundaries (e.g. BPS, GADM or geoBoundaries ADM1) or a land/water mask. The grid arithmetic (288 = 18 × 16 cells at 0.25°; 72 = 9 × 8 at 0.5°) is exact.

**Partial-cell weighting.** The 18 southern boundary cells at 0.25° lie only 60% inside the box (9 cells, 80%, at 0.5°). Detections are clipped to the box, yet each partial cell counts as one full cell in the denominator, so these cells have a lower chance of being occupied. The size of this effect has not been quantified.

**Leave-one-year-out on the real 2019–2024 data (Stage 4).** `scripts/run_loo_diagnostic.py` classifies each year-month against the threshold of the other five years (`baseline.compute_loo_classification`) and compares it with the released in-sample label. It first checks that its in-sample labels reproduce `calendar.json` exactly.

| Configuration | Sensor | Changed / evaluable | Direction |
|---|---|---|---|
| `primary` (0.25°, q 0.75) | MODIS | 0 / 72 | — |
| `viirs_primary_grid` (0.25°, q 0.75) | VIIRS | 0 / 72 | — |
| `modis_coarse_grid` (0.5°, q 0.75) | MODIS | 0 / 72 | — |
| `viirs_coarse_grid` (0.5°, q 0.75) | VIIRS | 0 / 72 | — |
| `modis_strict_threshold` (0.25°, q 0.90) | MODIS | 3 / 72 (2020-02, 2020-04, 2023-09) | not → elevated |

For q = 0.75 the zero changes are a property of the estimator with six values (both rules select the top two years), not evidence of robustness. The three q = 0.90 changes would not change any cross-configuration stability label: all three periods are already `classification_sensitive` and VIIRS stays not elevated (2020-02, 2020-04) or mixed (2023-09). Leave-one-year-out uses the same six years, so it is a self-inclusion check, not independent validation.

**Historical-to-recent activity (primary configuration).** `recent_activity.json` compares 2025 (forward holdout) and January–October 2026 with the frozen 2019–2024 medians and q = 0.75 thresholds read from `calendar.json`. The build (`scripts/build_recent_activity.py`) verified that re-aggregating 2019–2024 from the same source files reproduces `calendar.json` (72 months per sensor; 0 detection-count and occupied-cell mismatches; maximum occupied-cell-fraction difference 4.4×10⁻⁷, the JSON rounding). Archive and NRT files share no acquisition dates and are contiguous (MODIS archive to 2026-08-31, NRT from 2026-09-01; VIIRS archive to 2026-07-31, NRT from 2026-08-01). Results:

| Sensor | 2025 elevated (of 12) | 2026 elevated (of 10 with data) |
|---|---|---|
| MODIS | Feb, Jun, Jul (3) | Jan, Feb, Mar, May, Jun, Jul, Aug, Sep, Oct (9) |
| VIIRS | May, Jun (2) | Jan, Mar, Jun, Jul, Aug, Sep, Oct (7) |
| Both | Jun | Jan, Mar, Jun, Jul, Aug, Sep, Oct |

This is a forward comparison against a frozen reference, not independent validation. It tests the primary configuration only, uses six values per calendar month, mixes NRT months into late 2026, and has no reference fire data. The count of elevated 2025 months alone does not establish whether 2025 was typical. Days with detections are not observation coverage. November–December 2026 are missing, not zero.

**Stage 6B independent audit (disclosures).** The full audit is `STAGE_6B_SCIENTIFIC_AUDIT.md` (repository root). It reproduced all released results exactly and found three P1 interpretation issues and statistical qualifications, disclosed here without changing any result:

- **MODIS collection change (P1-1).** Every MODIS archive record from 2019–2022 is Collection 6 (`6.03`); every record from January 2023 is Collection 6.1 (`61.03`); NRT is `6.1NRT`. The 2019–2024 MODIS baseline combines two product collections (4 : 2 years), so 2023–2024 MODIS anomalies and the 2025–2026 MODIS comparisons may partly reflect the product change.
- **Terra/Aqua observation-time drift (P1-2).** Median daytime detection time of retained detections (local time, UTC+7): Terra about 10:35 (2019) → 08:39 (2026); Aqua about 13:41 → 15:43. Fire activity varies through the day, so these shifts can change detected activity independently of fire conditions. MODIS 2025–2026 comparisons are qualified accordingly. VIIRS (NOAA-20, product version 2 throughout) has a stable median daytime detection time of about 13:30–13:45 local in every year (Stage 6B.1 check); this makes it more homogeneous over time, not a ground truth or an equivalent replacement for MODIS.
- **FIRMS `type` field not filtered (P1-3).** The pipeline does not filter the archive `type` code, so retained detections can include sources flagged as static land sources (2), offshore (3) or volcanoes (1). Audit measurements for 2019–2024: 4,579 VIIRS detections (3.1% of retained VIIRS) and 133 MODIS detections (0.4%); excluding them would change occupied cells in 67/72 VIIRS and 45/72 MODIS months, by at most 2.8 and 1.4 percentage points, and would change one primary MODIS elevated label (2024-12) and no primary VIIRS label. Filtering is not applied in this release; NRT files carry no `type` field.
- **Spearman p-value (P2-1).** `sensors.json` → `overlap_diagnostics.spearman_p` (1.3 × 10⁻³³, ρ = 0.937, n = 72) assumes independent observations. The monthly series are autocorrelated (lag-1 rank autocorrelation about 0.65) and share a seasonal cycle, so the p-value must not be interpreted as though the 72 months were independent; it overstates precision. The statistic is reported unchanged; the audit's effective-sample-size estimate (about 29) is an approximation and is not used by the release. The previously noted 4 × 10⁻¹⁵ relative difference between library versions is floating-point noise and immaterial.
- **Reliability (P2-4, P2-5).** Stability labels show agreement across five tested configurations that share the same observations (3 MODIS, 2 VIIRS) and are not independent datasets. `consistently_elevated` requires the month to be the top year in the q = 0.90 MODIS configuration and top-two in the four q = 0.75 configurations; 5 of the 26 `classification_sensitive` months are sensitive only because of the q = 0.90 configuration. Leave-one-year-out at q = 0.75 yields zero changes by construction; at q = 0.90 it changes 3 of 72 classifications, none of which alters a reported stability label.
- **Provenance (P2-2).** The FIRMS retrieval date and requested date range are not recorded; the NASA readme files are link stubs.

**Open items.** Validation of the classifications against independent reference data, the five-configuration reliability labels for 2025–2026, temporal holdout of any harmonization (§9 item 2), and confirmation of the bounding box against provincial boundaries (§9 item 3) have not been done.

---

## 1. Methodology

Every pipeline module was read in full before any change was made.  
Findings were reproduced with executable Python probes before fixes were applied.  
Tests were added for every corrected behaviour.

---

## 2. Issues found and resolved

### 2.1 Critical — MODIS confidence field format (was: incorrect filter)

**Finding:**  
`MODIS_CONFIDENCE_KEEP` was defined as `{"nominal", "high", "n", "h"}`.  
NASA FIRMS MODIS active-fire CSV files store confidence as an **integer 0–100**, not a string. The current M-C61 archive manifest records both `6.03` and `61.03` product versions; the internal `MODIS_C61` sensor key does not mean every source record is exclusively Collection 6.1.
Confirmed from NASA Earthdata FIRMS FAQ:  
> *"For MODIS, the confidence value ranges from 0% to 100% and can be used to assign one of the three fire classes (low-confidence fire, nominal-confidence fire, or high-confidence fire)."*

**Impact before fix:**  
Every real MODIS row would have been excluded because string-comparison of integers against `{"nominal","high"}` always fails. The pipeline would have produced empty MODIS outputs on real data with no error raised.

**Fix:**  
- Replaced `MODIS_CONFIDENCE_KEEP` with `MODIS_CONFIDENCE_MIN_INT = 30` in `config.py`.
- `normalize.py`: numeric cast first; keep ≥ 30 (nominal + high); fallback to string labels for NRT files that use text.
- `validate.py`: same numeric logic for counting.
- Fixture regenerated with integer confidence values (85, 72, 95, 50, 88, 91, 76, 15, 5...).
- 9 new confidence tests added covering boundary values, mixed formats, both sensors.

**Mapping (from FIRMS documentation):**  
| Integer range | Class |
|---|---|
| 0–29 | low-confidence — excluded |
| 30–79 | nominal-confidence — kept |
| 80–100 | high-confidence — kept |

---

### 2.2 Scientific — Elevated threshold was global, not per-calendar-month

**Finding:**  
`compute_anomalies` computed:
```
threshold = quantile(all non-missing OCF values, q)
```
This is a **global** quantile mixing all 12 calendar months.  
For a region with strong seasonality (South Sumatra peaks in Aug–Oct):  
- September values would almost always exceed a global 75th percentile.  
- February values would almost never exceed it.  
This means the threshold would flag peak-season months as "elevated" compared to the whole year, not compared to other Septembers — the wrong scientific question.

**Fix:**  
Replaced with a **per-calendar-month** quantile:  
```
threshold[month] = quantile(OCF values for same calendar month, q)
```
Stored as a column `elevated_threshold` so each row's threshold is traceable.  
Classification now answers: *"Is this September anomalously high relative to other Septembers?"*

**Limitation preserved:**  
With ≤ 6 observations per calendar month (2019–2024), quantile estimates are highly uncertain. Months with fewer than `MIN_BASELINE_MONTHS=3` observations receive `insufficient_evidence`.

---

### 2.3 Grid denominator included cells outside the bounding box

**Finding:**  
`_build_grid_index` used `np.ceil(lon_max/res)*res` as the upper bound for `np.arange`, then `np.meshgrid` without filtering.  
For `bbox=(101.5, -4.9, 106.0, -1.0)` at 0.25°:  
- `floor(-4.9/0.25)*0.25 = -5.0` — below `lat_min=-4.9` → should be excluded.  
- `18 cells at lat=-5.0` were included in `total_eligible_cells=288`.  
This inflates the denominator by 18/288 ≈ 6.25%, deflating all OCF values.  
Identical issue at 0.5° (9 extra cells out of 72, +12.5%).

**Fix:**  
Strict bbox filter after grid construction:
```python
grid = grid[
    (cell_lon >= lon_min) & (cell_lon < lon_max) &
    (cell_lat >= lat_min) & (cell_lat < lat_max)
]
```
Corrected cell counts: **270** (was 288) at 0.25°, **63** (was 72) at 0.5°.

> **Superseded (§12.1).** This filter defines what is now Convention A, which is kept only as a sensitivity value. The approved primary grid is Convention B: every cell intersecting the bounding box, 288 cells at 0.25° and 72 at 0.5°, with all in-bounds detections counted.

---

### 2.4 Upper-edge detections were silently lost from occupied-cell count

**Finding:**  
A detection at exactly `lon=106.0` (the bbox upper edge) was assigned to cell `lon=106.0` by `_assign_grid_cells`, but that cell does not exist in the grid index (which uses half-open intervals).  
The occupied-cell count would be correct, but the cell would never match any grid cell for the denominator consistency assertion, and future geospatial joins would fail.

**Fix:**  
`_assign_grid_cells` now accepts an optional `bbox` parameter. When provided, coordinates at or beyond the upper edges are nudged inward (`lon_max - 1e-9`) before cell assignment, ensuring all in-bbox detections map to valid grid cells.

---

### 2.5 `is_fixture` flag never propagated

**Finding:**  
`reliability.py` hardcoded `is_fixture = False` for every output row.  
`export.py` did not accept or forward the flag.  
Result: fixture-derived JSON files were indistinguishable from real NASA outputs.

**Fix:**  
- `run_reliability_experiment()` now accepts `is_fixture: bool` parameter.
- `export_all()`, `export_regions()`, `export_calendar()`, `export_sensors()` accept `is_fixture`.
- When `True`, all five JSON files include:  
  `"is_fixture": true`  
  `"fixture_warning": "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT"`
- `run_pipeline.py` passes `is_fixture=use_fixtures` through the whole chain.

---

### 2.6 `validate.rows_accepted` overstated the final row count

**Finding:**  
`validate_raw` estimated `rows_accepted` as rows without bad coordinates or timestamps, but did not subtract low-confidence, out-of-bbox, or duplicate rows. The manifest therefore reported a higher number than `normalize` actually produced (12 vs 8 in the fixture).

**Fix:**  
Renamed the concept to an upper-bound estimate and added a note:  
`"rows_accepted is an upper-bound estimate; low-confidence and duplicate rows are excluded in normalize.py"`

---

### 2.7 `harmonize.py` was entirely absent

**Finding:**  
The `pipeline/` package had no overlap diagnostic module.

**Fix:**  
Created `pipeline/harmonize.py` with:
- `compute_overlap_diagnostics()` — identifies common periods, computes Spearman rank correlation, mean ratio, mean absolute difference.
- `OverlapDiagnostics` dataclass — structured result with limitations always populated.
- `diagnostics_to_dict()` — JSON-serialisable output.
- Explicit policy: `harmonization_supported = False` always, until holdout validation is performed.
- 11 tests in `tests/test_harmonize.py`.
- Wired into `run_pipeline.py` and `export_sensors()`.

---

## 3. Issues reviewed and not changed

### 3.1 Deduplication key difference (validate vs normalize)

`validate.py` counts duplicates using string fields `(latitude, longitude, acq_date, acq_time)`.  
`normalize.py` deduplicates on `(latitude, longitude, acq_datetime_utc)` after parsing.  
These are logically equivalent for the same record but technically different keys.  
**Decision:** no change — `validate` only counts for the manifest; `normalize` performs the actual dedup. The discrepancy is acceptable and the behaviour is documented.

### 3.2 `config.py` directory creation at import time

Side-effect import behaviour. Acceptable for a single-process scientific pipeline.  
Not changed.

### 3.3 `np.arange` floating-point precision

Verified: for the specific bbox and resolutions used, `np.arange` produces exact multiples of the resolution step. Combined with `round(x, 10)`, no rounding errors accumulate.  
Not changed.

---

## 4. Reliability configuration defensibility

The version-2 registry contains five configurations:

| Name | Sensor | Grid | Baseline | Quantile | Defensibility |
|---|---|---|---|---|---|
| `primary` | MODIS (`MODIS_C61` key) | 0.25° | 2019–2024 | 75th pct | **Defensible baseline** |
| `viirs_primary_grid` | VIIRS J1 C2 | 0.25° | 2019–2024 | 75th pct | **Tests cross-sensor stability** |
| `modis_coarse_grid` | MODIS (`MODIS_C61` key) | 0.5° | 2019–2024 | 75th pct | **Tests grid-resolution sensitivity** |
| `modis_strict_threshold` | MODIS (`MODIS_C61` key) | 0.25° | 2019–2024 | 90th pct | **Tests threshold sensitivity** |
| `viirs_coarse_grid` | VIIRS J1 C2 | 0.5° | 2019–2024 | 75th pct | **Tests grid-resolution sensitivity** |

Registry v1 recorded the first four configurations; v2 adds `viirs_coarse_grid`.
**Source provenance:** The current MODIS archive records product versions `6.03` and `61.03`; separate NRT inputs record `6.1NRT`. NRT provenance is retained separately, and the analysis is restricted to 2019–2024.
**Scientific note:** These five configurations vary three dimensions (sensor, grid, threshold). With 2019–2024 data only (~6 observations per calendar month), classification stability should be interpreted as an experiment in analytical sensitivity, not as a measure of observational uncertainty.

---

## 5. Short-baseline limitations (2019–2024)

Explicitly documented in every output:

- Maximum 6 observations per calendar month for seasonal baselines.
- Quantile thresholds computed from ≤ 6 values per calendar month — highly uncertain.
- `MIN_BASELINE_MONTHS = 3`: months with fewer observations receive `insufficient_evidence`.
- The 2019–2024 period cannot be claimed as long-term climatology.
- Results labelled as **indicative, not definitive** in all JSON outputs and documentation.

---

## 6. Data availability for real NASA processing

*Updated for the release candidate. The Phase 2 text recorded `data/raw/` as empty; real FIRMS files have since been processed (§0).*

**Raw source files are not included in the public release.** `.gitignore` excludes `data/raw/`. To reproduce the outputs, download the FIRMS CSVs separately (see `docs/DATA_DOWNLOAD.md`). The files used for the released outputs are identified in `data/manifests/` by filename, request ID, repository-relative path, SHA-256 hash and row counts, so a new download can be checked against them.

**Layout and naming** (same as `docs/DATA_DOWNLOAD.md`). Keep NASA's original filenames and separate archive from NRT files:
```
data/raw/modis/archive/fire_archive_M-C61_<request-id>.csv
data/raw/modis/nrt/fire_nrt_M-C61_<request-id>.csv
data/raw/viirs/archive/fire_archive_J1V-C2_<request-id>.csv
data/raw/viirs/nrt/fire_nrt_J1V-C2_<request-id>.csv
```

**Required columns** (lowercase after ingestion; `pipeline/config.py`):
- MODIS (`MODIS_REQUIRED_COLUMNS`): `latitude, longitude, brightness, scan, track, acq_date, acq_time, satellite, confidence, version, bright_t31, frp, daynight`
- VIIRS (`VIIRS_REQUIRED_COLUMNS`): `latitude, longitude, scan, track, acq_date, acq_time, satellite, confidence, version, frp, daynight`

**Verified VIIRS source headers.** The headers of the two VIIRS source files used for the released outputs (request 849851) were inspected directly:

| File | Header | Confidence values (count) |
|---|---|---|
| `fire_archive_J1V-C2_849851.csv` | `latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type` | `n` 155,074 · `l` 8,071 · `h` 5,421 (total 168,566) |
| `fire_nrt_J1V-C2_849851.csv` | same, without `type` | `n` 61,263 · `l` 3,032 · `h` 2,280 (total 66,575) |

The totals equal `rows_raw` and the `l` counts equal `low_confidence_rows` in `data/manifests/VIIRS_J1_C2_manifest.json`. `type` appears only in the archive export and is not required. `l` rows are excluded and `n`/`h` rows retained (`VIIRS_CONFIDENCE_KEEP`). The thermal fields are named `brightness` and `bright_t31`; their mapping to VIIRS I4/I5 is unverified, so the pipeline does not require, alias or use them for VIIRS. (An earlier version of this section listed `bright_ti4`/`bright_ti5`; those names do not occur in the verified exports.) Only these two headers and their confidence codes were verified; other FIRMS export variants, future schema changes and the `acq_time` text format were not. Where an `instrument` column is present it must be `MODIS` or `VIIRS` respectively. Platform identifiers must be Terra/Aqua for MODIS and NOAA-20 (`N20` in the processed files) for VIIRS.

**Confidence field format** (sensor-specific; not equivalent across sensors):
- MODIS: **integer 0–100**; keep ≥ 30 (nominal + high).
- VIIRS: **string** `low`/`nominal`/`high`, or `l`/`n`/`h`; keep `nominal`/`high`.

**To run with real data:**
```bash
python scripts/run_pipeline.py
```

---

## 7. Memory and large-file handling

`ingest.py` uses `pd.read_csv(..., dtype=str, low_memory=False)` on each file individually, then concatenates. For typical FIRMS archive sizes (South Sumatra, 6 years):
- MODIS: ~50,000–200,000 rows estimated — fits in RAM with margin.
- VIIRS: ~100,000–500,000 rows estimated — fits in RAM with margin.

For unexpectedly large files (>1M rows), chunked reading can be added to `_load_csv` without changing downstream logic. No change made now — the need has not been demonstrated with real data.

---

## 8. Test summary

**Current:** Python 325 passed (`python -m pytest tests/`, 20 test files, including `test_recent_activity.py`); frontend 26 passed (`npm test` in `web/`, 4 files). The Python count includes manifest-path portability and resolver tests (`test_manifest_portability.py`, `test_manifest_resolver.py`) and fixture schema checks against the verified VIIRS source headers (`test_fixture_schema.py`).

**Historical — Phase 2 (89 tests):**

| Test file | Tests | Coverage |
|---|---|---|
| `test_validate.py` | 9 | Schema errors, coordinate checks, bbox, duplicates, confidence |
| `test_normalize.py` | 10 | Exclusion counts for all filter types, sensor tags, type casting |
| `test_confidence.py` | 13 | MODIS integer 0-100, boundary values, VIIRS strings, fallbacks |
| `test_aggregate.py` | 10 | Month completeness, OCF range, missing=null, sensor separation |
| `test_grid.py` | 12 | Cell counts, bbox filter, edge clamping, denominator stability, OCF≤1 |
| `test_baseline.py` | 8 | Seasonal baseline, insufficient data, anomaly labels |
| `test_reliability.py` | 5 | All three Blueprint §08 scenarios + empty input |
| `test_harmonize.py` | 11 | Overlap counting, Spearman, ratio, harmonization guard, serialisability |
| `test_fixture_guard.py` | 10 | JSON provenance fields, fixture flags, null semantics, guardrails |
| **Total** | **89** | **All pass** |

---

## 9. Remaining blockers (Phase 2)

1. **Superseded.** *Phase 2 text: "Real NASA FIRMS data not yet downloaded. All outputs currently use synthetic fixtures and are labelled `is_fixture: true`."* Real FIRMS data have since been processed and the released contracts are `is_fixture: false` (§0).

2. **Temporal holdout validation not performed.** `harmonize.py` correctly refuses calibration without holdout data. Harmonization remains unsupported until a sufficient overlap period (≥ 12 months) is validated.

3. **Bounding box confirmation.** The bbox `(101.5, -4.9, 106.0, -1.0)` is from the Blueprint §3.1. Exact coverage should be confirmed against the FIRMS download boundary before publication.

---

## 10. Recommended next action (Phase 2 — historical, completed)

Download real NASA FIRMS CSV archives (see `docs/DATA_DOWNLOAD.md`) and run:
```bash
python scripts/run_pipeline.py
```
Verify the manifest files in `data/manifests/` report non-zero row counts, then review the generated JSON outputs.

---

## 11. Phase 3 corrections

**Test result:** 149 passed. Primary metric definition unchanged.

### 11.1 Grid coverage: geographic support of the primary metric

The bbox south edge (lat -4.9) is not on a 0.25° or 0.5° grid line, so the two conventions differ.

> **Superseded (§12.1).** The roles below are as of Phase 3. Convention B is now the approved primary grid and Convention A is a sensitivity value. The definitions and the coverage table remain accurate.

- **Convention A (Phase 3 primary; now sensitivity only):** cells whose lower-left origin lies in [lon_min, lon_max) x [lat_min, lat_max). Every cell lies fully inside the bbox.
- **Convention B (Phase 3 diagnostic; now primary):** every cell that intersects the bbox.

| Quantity (square degrees, not km2) | 0.25° | 0.5° |
|---|---|---|
| Bbox area | 17.55 | 17.55 |
| A: eligible cells (denominator) | 270 | 63 |
| A: area covered | 16.875 | 15.75 |
| A: bbox area not covered (southern strip) | 0.675 (3.85%) | 1.80 (10.26%) |
| B: eligible cells | 288 | 72 |
| B: area covered | 18.00 | 18.00 |
| B: cell area outside the bbox | 0.45 | 0.45 |
| Denominator ratio B/A | 1.067 | 1.143 |

Effect on OCF:
- With identical occupied cells, OCF_B = OCF_A x (A cells / B cells), i.e. x0.9375 at 0.25° and x0.875 at 0.5°.
- Convention A drops detections in the southern strip from OCF, Convention B keeps them. The two effects pull in opposite directions, so B is not systematically lower. On one synthetic example (60 uniform random points, mechanism check only, not a result): 0.25° gave OCF_A 0.174 vs OCF_B 0.177; 0.5° gave 0.556 vs 0.542.
- A month whose only detections fall in the strip has `has_data=false` under A and `true` under B.

**Geographic support statement:** the primary index describes 96.2% (0.25°) or 89.7% (0.5°) of the bounding box, the part north of the first grid line. The southern strip is reported in `detection_count` and `partial_cell_detections` only. The 0.5° sensitivity configuration therefore covers a different area than the 0.25° primary, which is part of what the grid-sensitivity configuration measures.

**Decision status (Phase 3 — superseded by §12.1, which approved Convention B as primary):** Convention A stays the primary metric. Switching to B, or moving the bbox to a grid line, changes the metric and needs explicit approval. Tools: `grid_geographic_support()` and `compare_grid_conventions()` in `pipeline/aggregate.py`. The geographic support is also exported in `methodology.json` under `geographic_support`.

### 11.2 Seasonal self-inclusion: scope of the simulation result

The earlier "0% change in 10,000 cases" came from a random simulation with these assumptions:
- baseline of 5 values plus the target year (6 in total), q = 0.75, linear-interpolation quantiles (numpy default);
- target and baseline drawn independently from the same distribution (exponential, scale 0.1);
- seed 42.
That OCF follows these distributions is an assumption, not something checked against real data.

A later check re-ran it with uniform, lognormal and beta draws (0% each), then replaced sampling with an exhaustive rank enumeration. With no ties, only the rank of the target among baseline values matters, so every case can be listed.

| Total observations | q = 0.75 | q = 0.90 |
|---|---|---|
| 4 (3 baseline + target) | no change | no change |
| 5 (4 baseline + target) | **changes when target ranks 4th of 5** | no change |
| 6 (5 baseline + target) | no change | no change |
| 7 (6 baseline + target) | no change | no change |

> **Correction (Stage 4 real-data check).** The q = 0.90 column is wrong for 6 observations. The rank enumeration only holds when the leave-one-out quantile falls exactly on a data point. With 5 remaining values, q = 0.75 does (the 4th value), but q = 0.90 interpolates between the 4th and 5th values, so the outcome depends on their spacing, not only on rank. On the real data, `modis_strict_threshold` (q = 0.90) changed 3 of 72 classifications (see §0). For q = 0.75 with 6 observations and no ties, leave-one-out and in-sample classifications are identical by construction.

Scope of the claim: no classification change for 6 or 7 observations at q = 0.75 and 0.90, assuming no ties and linear interpolation (corrected above: not valid for q = 0.90 with 6 observations). It does not hold for 5 observations at q = 0.75, which is the case when one baseline year is missing. Ties (for example identical OCF values in two years) were not tested. Other quantiles and other n were not tested.

The leave-one-year-out diagnostic (`compute_loo_classification`) stays. It still needs checking against real observations once they exist. Regression tests: `TestSelfInclusionExhaustive`.

### 11.3 Reliability: minimum evaluable configurations

Problem found: with the old rule, one elevated configuration plus three `insufficient_evidence` configurations produced `consistently_elevated`. One configuration is not agreement.

Rule now (`RELIABILITY_MIN_EVALUABLE_CONFIGS = 2`, fixed before any real-data run):
1. Evaluable configuration = result is `consistently_elevated` or `not_elevated`.
2. Fewer than 2 evaluable configurations: `insufficient_evidence`.
3. 2 or more, all elevated: `consistently_elevated`; all not elevated: `not_elevated`; mixed: `classification_sensitive`.
4. `insufficient_evidence` configurations are never counted as agreement.

Coverage is now reported per period in `reliability.json`: `n_evaluable`, `min_evaluable_required`, `evaluable_fraction`, plus the top-level `min_evaluable_configs`. Existing fields are unchanged (additive change to contract 1.0.0).

Independence caveat, added to `reliability.json` limitations: three of the four configurations use MODIS, so agreement among them is weaker evidence than agreement across sensors. A period where only MODIS configurations are evaluable can still be labelled `consistently_elevated`. Whether to require at least one evaluable configuration from each sensor is an open scientific decision for approval.

> **Superseded (§12.2, §13).** The cross-sensor requirement was approved in §12.2, and registry v2 (§13) has 5 configurations, 3 MODIS and 2 VIIRS.

### 11.4 Other correction

The fixture warning was missing from `reliability.json` and `methodology.json`, although the Phase 2 note said all five files carried it. All five contracts now carry `is_fixture`, and `fixture_warning` when true. `test_every_file_declares_fixture_status_and_warning` enforces it.

### 11.5 Open decisions needing approval (Phase 3 — both resolved in §12)

1. Keep Convention A as the primary grid, or move to Convention B or a grid-aligned bbox. **Resolved in §12.1: Convention B is primary.**
2. Whether a stability label must include at least one evaluable configuration per sensor. **Resolved in §12.2: yes.**

---

## 12. Final scientific decisions (approved) — processing version 0.2.0, contract 1.1.0

**Test result:** 214 passed. All outputs were still synthetic fixtures (`is_fixture: true`) at this stage; real data were processed later (§0).

### 12.1 Primary grid: Convention B

- **Primary (B):** every grid cell intersecting the bounding box is eligible. Every in-bounds detection is included.
- **Sensitivity (A):** cells whose lower-left origin lies inside the box. Exported as `occupied_cell_fraction_convention_a` and `occupied_cells_convention_a` next to each primary value in `calendar.json`.

| Resolution | B eligible cells | B fully interior | B partial boundary cells | A eligible cells |
|---|---|---|---|---|
| 0.25° | 288 | 270 | 18 | 270 |
| 0.5° | 72 | 63 | 9 | 63 |

All partial boundary cells are in the southern row (cell origin lat -5.0). They extend 0.1° below the box edge at -4.9. The other three box edges lie on grid lines.

Provenance: every aggregated row and every `calendar.json` month carries `grid_convention`, `total_eligible_cells`, `partial_boundary_cells` and `partial_cell_detections`. The latter counts detections that fell in a cell not fully inside the box. `calendar.json` and `methodology.json` include `metric_definitions` for A and B.

**Interpretation:** `occupied_cell_fraction` is a ratio of cell counts. Each eligible cell has weight 1, including boundary cells partly outside the box. It is not area-weighted, not converted to km2, and not a burned-area, fire-count or severity measurement.

**Versioning:** `PROCESSING_VERSION` 0.1.0 → 0.2.0. Primary values are not comparable with 0.1.0 outputs: the denominator changed from 270 to 288 at 0.25°, and strip detections are now counted. `CONTRACT_VERSION` 1.0.0 → 1.1.0. The change is additive: no field was removed or renamed, and a test checks every 1.0.0 calendar field is still present. Frontend-visible changes:
- new fields listed above;
- a new stability label value, `insufficient_cross_sensor_evidence`;
- a `sensor_specific` object per reliability period.

All four reliability configurations now record `grid_convention: "B"`. Within the reliability experiment the grid-sensitivity dimension is resolution only (0.25° vs 0.5°). The A/B comparison is reported separately. Under B, 0.25° and 0.5° cover the same box edges, so the earlier problem of the 0.5° configuration covering a different area no longer applies.

### 12.2 Cross-sensor reliability rule

A cross-sensor agreement label (`consistently_elevated`, `not_elevated`, `classification_sensitive`) requires both:
1. at least 2 evaluable configurations overall, and
2. at least 1 evaluable MODIS configuration and at least 1 evaluable VIIRS configuration.

Otherwise:
- fewer than 2 evaluable configurations → `insufficient_evidence`;
- 2 or more evaluable, but MODIS or VIIRS has none → `insufficient_cross_sensor_evidence`.

"Evaluable" means the configuration returned elevated or not_elevated. Two things are never counted as agreement: `insufficient_evidence` results, and configurations that did not run, for example because one sensor had no data. Non-running configurations are now counted (`n_not_run`) and stay in the denominator of `evaluable_fraction`.

Sensor-specific findings are always kept in `sensor_specific` per period, using separate labels: `elevated`, `not_elevated`, `mixed`, `insufficient_evidence`. These describe one sensor only and are not agreement labels. A sensor-specific label can rest on one configuration. MODIS has 3 configurations and VIIRS has 1, so VIIRS evidence always rests on a single configuration. Sensor disagreement shows sensitivity to sensor choice; it does not show which sensor is closer to actual fire occurrence.

The rule was tested against all 81 combinations of the three possible results across the four configurations (`test_exhaustive_rule`).

### 12.3 Remaining blockers (as of processing 0.2.0 — both superseded)

> **Superseded.** Item 1: real FIRMS data have since been processed (§0); validating the leave-one-year-out diagnostic against real observations is not documented as done. Item 2: registry v2 (§13) added a second VIIRS configuration.

1. **No real NASA data.** `data/raw/modis/` and `data/raw/viirs/` are empty. Nothing has been validated against real observations, including the leave-one-year-out diagnostic.
2. **VIIRS has one configuration.** With the cross-sensor rule, any period where that VIIRS configuration is insufficient gets no cross-sensor label. Adding VIIRS configurations would be a new pre-declared configuration and needs approval before real data are processed.


---

## 13. Reliability configuration registry v2 — processing version 0.3.0, contract 1.2.0

**Test result:** 233 passed at this stage (current count: §8). Fixture pipeline ran without errors. All outputs were still synthetic fixtures (`is_fixture: true`) at this stage; real data were processed later under the same processing version 0.3.0 (§0).

### 13.1 Change

One configuration added (approved before any real-data run):

| Name | Sensor | Grid | Convention | Baseline | Quantile |
|---|---|---|---|---|---|
| `viirs_coarse_grid` | VIIRS J1 C2 | 0.5° | B | 2019–2024 | 0.75 |

It mirrors `modis_coarse_grid` except for the sensor, so grid-resolution sensitivity is now tested for both sensors.

Unchanged:
- the four existing configurations;
- `RELIABILITY_MIN_EVALUABLE_CONFIGS = 2`;
- the cross-sensor requirement (at least 1 evaluable MODIS and 1 evaluable VIIRS configuration);
- every label rule.

Tests pin each existing configuration's parameters.

Declared set is now 5 configurations: 3 MODIS, 2 VIIRS.

| Registry version | Configurations |
|---|---|
| 1 | primary, viirs_primary_grid, modis_coarse_grid, modis_strict_threshold |
| 2 | + viirs_coarse_grid |

### 13.2 Effects

- `n_configs_total` per period is now 5 (MODIS 3, VIIRS 2 in `sensor_specific`).
- `evaluable_fraction` denominators change: 2 evaluable of 5 is 0.4, where it was 0.5 of 4.
- VIIRS evidence for the cross-sensor requirement can now come from either VIIRS configuration. If `viirs_primary_grid` is insufficient, `viirs_coarse_grid` can still satisfy it. The VIIRS sensor-specific label can now be `mixed`.
- Two evaluable VIIRS configurations with no evaluable MODIS configuration meet the overall minimum of 2 but still give `insufficient_cross_sensor_evidence`.
- If VIIRS data are absent, both VIIRS configurations count as not run (`n_not_run = 2`), and no period receives a cross-sensor agreement label.
- The two VIIRS configurations share a sensor and baseline, so they are not independent. Agreement between them is grid-resolution stability, not independent confirmation.

The rule was tested against all 243 result combinations across the five configurations (`tests/test_registry_v2.py`).

### 13.3 Versioning

- `PROCESSING_VERSION` 0.2.0 → 0.3.0. The primary metric is identical to 0.2.0. Reliability labels can differ from 0.2.0 because the configuration set changed.
- `CONTRACT_VERSION` 1.1.0 → 1.2.0. The change is additive:
  - `reliability.json`: `config_registry_version`, `config_registry_history`;
  - `methodology.json`: `reliability_config_registry_version`.
- No field removed or renamed. No new label values.

### 13.4 Status

Backend feature work stops here. The next priority is integrating real NASA FIRMS archives, which is blocked until the CSV files are placed in `data/raw/modis/` and `data/raw/viirs/`.

> **Superseded.** Real FIRMS archives (requests 849850 and 849851) have since been integrated; see §0.
