# Obtaining NASA FIRMS Data

## Overview

FireChronicle requires official NASA FIRMS CSV archives.  
You cannot substitute other data sources and represent outputs as NASA-derived.

Raw FIRMS CSV files are not distributed with this repository; `.gitignore`
excludes `data/raw/`. Download them yourself as described below.

## Product selection

| Sensor | Product | Collection | Download path |
|--------|---------|------------|---------------|
| MODIS  | MOD14 / MYD14 Active Fire | C6 and C6.1 records (FIRMS M-C61 request; version IDs are manifest-tracked) | `data/raw/modis/` |
| VIIRS  | VNP14IMGTDL_NRT / VJ114IMGTDL | Collection 2, NOAA-20 (J1) | `data/raw/viirs/` |

## Region and time window

- **Bounding box**: longitude 101.5–106.0, latitude −4.9–−1.0 (South Sumatra)
- **Time window**: 2019–2024
- **Format**: CSV (the pipeline does not parse HDF or NetCDF)

## Download options

### Option A — FIRMS Archive Download (recommended)

1. Go to: https://firms.modaps.eosdis.nasa.gov/download/
2. Create a free NASA Earthdata account if you do not have one.
3. Select **Archive Download** → choose the product, region (use the bounding box above), and date range.
4. Download the resulting CSV(s).
5. Preserve archive and NRT files separately:
   - `data/raw/modis/archive/` and `data/raw/modis/nrt/`
   - `data/raw/viirs/archive/` and `data/raw/viirs/nrt/`
   The ingestion step discovers CSVs recursively and records filename, request
   ID, product code, processing status, and SHA-256 in each sensor manifest.
   Manifest paths are repository-relative with `/` separators (for example
   `data/raw/modis/archive/fire_archive_M-C61_849850.csv`), so manifests
   contain no machine-specific paths and stay valid in any clone location.
   Files that identify themselves as archive/NRT must have matching product
   versions. If archive and NRT acquisition dates overlap for a sensor,
   ingestion stops for that sensor until the overlap is resolved explicitly.

### Option B — FIRMS Map / Fire Archive

1. Go to: https://firms.modaps.eosdis.nasa.gov/map/
2. Set date range, region, and product.
3. Export as CSV.
4. Place files as above.

## Naming convention

The pipeline recursively discovers `*.csv` files in each sensor directory.
Keep NASA's original filenames and use `archive` or `nrt` subdirectories when
that processing status is known. Recognized NASA filenames also provide a
product code and request ID for provenance:

```
data/raw/modis/archive/fire_archive_M-C61_<request-id>.csv
data/raw/modis/nrt/fire_nrt_M-C61_<request-id>.csv
data/raw/viirs/archive/fire_archive_J1V-C2_<request-id>.csv
data/raw/viirs/nrt/fire_nrt_J1V-C2_<request-id>.csv
```

The VIIRS archive and NRT headers of the request-849851 files were verified
directly. Both contain
`latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight`;
the archive file adds a trailing `type` column, which the pipeline treats as
optional. VIIRS `confidence` uses `n`/`h`/`l`; `l` rows are excluded. The pipeline does not filter on `type`: retained archive detections can
include sources FIRMS flags as volcanoes (1), static land sources (2) or offshore
(3); see `docs/SCIENTIFIC_AUDIT.md` §0 for the measured effect. The export
does not provide verified names for I4/I5 thermal brightness fields. The
pipeline does not alias `brightness` or `bright_t31` to VIIRS I4/I5; these
unused thermal fields are not required for the current occupied-cell analysis.
Other or future FIRMS export variants have not been verified.

## Running the pipeline with real data

```bash
python scripts/run_pipeline.py
```

## Running with synthetic fixtures (no NASA download required)

```bash
python scripts/run_pipeline.py --fixture
```

Fixture outputs are labelled `is_fixture: true` in every JSON contract and must
not be presented as scientific results.

## Important scientific notes

- Missing months in the archive are labelled `null` in outputs, not zero.
- Do not combine MODIS and VIIRS raw counts into a single unqualified total.
- Record the product version and download date in your project documentation.
  The current manifests do not record the FIRMS download date or requested date range.
- The MODIS archive used here is Collection 6 (`6.03`) for 2019–2022 and Collection 6.1
  (`61.03`) from January 2023; record which collection a new download contains.
- Confirm the exact temporal coverage of your download before making baseline claims.
- The configured analysis and seasonal baseline remain 2019–2024. Later years
  are excluded during normalization until a separate baseline decision is approved.
