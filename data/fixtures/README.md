# FireChronicle — Test Fixtures

**These files contain SYNTHETIC data for unit testing only.**

They are clearly labelled and are NEVER used in scientific results,
frontend outputs or visualisations presented to users.

| File | Purpose |
|------|---------|
| `modis_sample.csv` | Minimal synthetic MODIS-format CSV, 12 rows |
| `viirs_sample.csv` | Minimal synthetic VIIRS-format CSV, 10 rows |

## Column definitions

Both files follow the NASA FIRMS CSV column names accepted by
`pipeline/validate.py` (see `MODIS_REQUIRED_COLUMNS` and
`VIIRS_REQUIRED_COLUMNS` in `pipeline/config.py`):
https://firms.modaps.eosdis.nasa.gov/

- **MODIS:** integer `confidence` (0–100), `satellite` `Terra`/`Aqua`.
- **VIIRS:** the header is identical (names and order) to the directly
  verified header of the FIRMS VIIRS NRT source file used for the released
  outputs (`fire_nrt_J1V-C2_849851.csv`):
  `latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight`.
  `confidence` uses the single-letter codes found in both verified source files
  (`n`, `h`, `l`); `satellite` is `N20`; `instrument` is `VIIRS`. The thermal
  columns `brightness` and `bright_t31` are the source's own names; their
  mapping to VIIRS I4/I5 bands is unverified, so the pipeline neither requires
  nor uses them for VIIRS.
- The verified VIIRS archive header is the NRT header plus a trailing `type`
  column. Both fixture files use NRT product versions (`6.1NRT`, `2.0NRT`) and
  therefore have no `type` column; `type` is optional in the pipeline.
- Only the two verified VIIRS source headers and their confidence codes were
  checked. Other optional fields, other FIRMS export variants and the MODIS
  source header have not been verified against this fixture.

Synthetic values are chosen to exercise:
- Valid rows (accepted)
- Low-confidence rows (excluded)
- Rows outside the South Sumatra bounding box (excluded after spatial filter)
- Duplicate rows (deduplicated)
- Rows outside the 2019–2024 year window (excluded; MODIS file only)
