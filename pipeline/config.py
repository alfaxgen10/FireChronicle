"""
FireChronicle pipeline configuration.

All analytically significant constants are centralised here so that
processing scripts import from one source of truth.  Changes to these
values constitute a new processing version and must be reflected in
exported JSON provenance fields.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Processing version
# ---------------------------------------------------------------------------
# 0.2.0: primary grid convention changed from A (cell origin inside bbox) to
#        B (every cell intersecting the bbox); cross-sensor reliability rule.
#        Primary metric values are NOT comparable with 0.1.0 outputs.
# 0.3.0: reliability configuration registry v2 (+ viirs_coarse_grid).
#        Primary metric unchanged from 0.2.0; reliability labels may differ
#        from 0.2.0 because the configuration set changed.
PROCESSING_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Region of interest — South Sumatra, Indonesia
# Bounding box from Engineering Blueprint §3.1 (confirmed against FIRMS AOI).
# Format: (lon_min, lat_min, lon_max, lat_max)
# ---------------------------------------------------------------------------
REGION_ID = "south_sumatra"
REGION_NAME = "South Sumatra, Indonesia"
BBOX = (101.5, -4.9, 106.0, -1.0)   # (lon_min, lat_min, lon_max, lat_max)

# ---------------------------------------------------------------------------
# Supported time window
# ---------------------------------------------------------------------------
YEAR_START = 2019
YEAR_END   = 2024

# ---------------------------------------------------------------------------
# Spatial grid
# Resolution in decimal degrees; 0.25° ≈ 25 km at the equator.
# Two sizes are tested in the reliability sensitivity experiment.
# ---------------------------------------------------------------------------
GRID_RESOLUTION_DEG_PRIMARY    = 0.25   # primary index
GRID_RESOLUTION_DEG_SENSITIVITY = 0.5   # alternative for sensitivity check

# ---------------------------------------------------------------------------
# Grid coverage convention (approved scientific decision)
#   "B" (PRIMARY)     : every grid cell that intersects the study bounding box
#                       is eligible; every in-bounds detection is included.
#                       Boundary cells extend partly outside the box.
#   "A" (SENSITIVITY) : only cells whose lower-left origin lies inside the box.
#                       Detections in the uncovered boundary strip are excluded
#                       from the occupied-cell fraction.
# The occupied-cell fraction is a count of cells, NOT an area-weighted measure
# and NOT a burned-area estimate.
# ---------------------------------------------------------------------------
GRID_CONVENTION_PRIMARY     = "B"
GRID_CONVENTION_SENSITIVITY = "A"

# ---------------------------------------------------------------------------
# Sensor / product identifiers
# Source: NASA FIRMS product catalogue.
# ---------------------------------------------------------------------------
SENSOR_MODIS = "MODIS_C61"
SENSOR_VIIRS = "VIIRS_J1_C2"

SENSOR_LABELS = {
    SENSOR_MODIS: "MODIS Terra / Aqua",
    SENSOR_VIIRS: "VIIRS NOAA-20 Collection 2",
}

# ---------------------------------------------------------------------------
# MODIS FIRMS CSV expected columns (subset that must be present)
# ---------------------------------------------------------------------------
MODIS_REQUIRED_COLUMNS = {
    "latitude", "longitude", "brightness", "scan", "track",
    "acq_date", "acq_time", "satellite", "confidence", "version",
    "bright_t31", "frp", "daynight",
}

# ---------------------------------------------------------------------------
# VIIRS FIRMS CSV columns needed by the current analysis.
# VIIRS thermal fields are intentionally not required: the downloaded FIRMS
# exports use brightness / bright_t31, whose mapping to I4 / I5 is unverified.
# ---------------------------------------------------------------------------
VIIRS_REQUIRED_COLUMNS = {
    "latitude", "longitude", "scan", "track",
    "acq_date", "acq_time", "satellite", "confidence", "version",
    "frp", "daynight",
}

# ---------------------------------------------------------------------------
# Confidence / quality filtering
#
# MODIS (C6.1): confidence is an INTEGER 0–100.
#   < 30         → low-confidence fire  (exclude)
#   30–79        → nominal-confidence fire (keep)
#   80–100       → high-confidence fire (keep)
#   Source: NASA FIRMS FAQ; MODIS C6.1 Active Fire User Guide.
#
# VIIRS (J1 C2): confidence is a STRING — "low", "nominal", or "high".
#   Some archive CSVs also use the single-letter abbreviations "l", "n", "h".
#   Source: NASA FIRMS FAQ; VIIRS Active Fire User Guide.
#
# The MODIS filter is applied as a numeric comparison in normalize.py.
# The VIIRS filter is applied as a string comparison.
# ---------------------------------------------------------------------------
MODIS_CONFIDENCE_MIN_INT = 30    # keep confidence >= 30 (nominal + high)

VIIRS_CONFIDENCE_KEEP = {"nominal", "high", "n", "h"}  # string labels in CSV

# ---------------------------------------------------------------------------
# Baseline window for seasonal anomaly calculation
# Must be declared before inspecting results (Blueprint §3.4).
# ---------------------------------------------------------------------------
BASELINE_YEAR_START = 2019
BASELINE_YEAR_END   = 2024   # full available window; updated when data extend

# ---------------------------------------------------------------------------
# Critical-period / reliability sensitivity configurations
# Each configuration is a named dict of overrideable parameters.
# The set is fixed before analysis; do not add post-hoc configurations.
# ---------------------------------------------------------------------------
# Reliability classification — minimum evaluable configurations
#
# A period can be labelled consistently_elevated or not_elevated only when
# at least this many configurations produced an evaluable result
# (elevated or not_elevated; insufficient_evidence does not count).
#
# Rationale: requiring ≥ 2 evaluable configurations prevents a single
# configuration from being presented as consensus agreement.  With 5
# declared configurations (3 MODIS, 2 VIIRS), 2 is a conservative minimum
# that remains achievable when some configurations lack sufficient data.
#
# This constant must be fixed before analysis and must not be changed
# post-hoc to increase or decrease the number of elevated periods.
# ---------------------------------------------------------------------------
RELIABILITY_MIN_EVALUABLE_CONFIGS = 2

# Cross-sensor agreement (approved scientific decision).
# A cross-sensor agreement label (consistently_elevated / not_elevated /
# classification_sensitive) requires at least RELIABILITY_MIN_EVALUABLE_PER_SENSOR
# evaluable configurations from EACH sensor in RELIABILITY_REQUIRED_SENSORS, in
# addition to RELIABILITY_MIN_EVALUABLE_CONFIGS overall. Otherwise the period is
# reported as insufficient cross-sensor evidence; sensor-specific findings are
# still retained. Missing configurations are never counted as agreement.
RELIABILITY_MIN_EVALUABLE_PER_SENSOR = 1
RELIABILITY_REQUIRED_SENSORS = (SENSOR_MODIS, SENSOR_VIIRS)

RELIABILITY_CONFIGS = {
    "primary": {
        "sensor": SENSOR_MODIS,
        "grid_deg": GRID_RESOLUTION_DEG_PRIMARY,
        "baseline_start": BASELINE_YEAR_START,
        "baseline_end": BASELINE_YEAR_END,
        "elevated_quantile": 0.75,
        "grid_convention": GRID_CONVENTION_PRIMARY,
    },
    "viirs_primary_grid": {
        "sensor": SENSOR_VIIRS,
        "grid_deg": GRID_RESOLUTION_DEG_PRIMARY,
        "baseline_start": BASELINE_YEAR_START,
        "baseline_end": BASELINE_YEAR_END,
        "elevated_quantile": 0.75,
        "grid_convention": GRID_CONVENTION_PRIMARY,
    },
    "modis_coarse_grid": {
        "sensor": SENSOR_MODIS,
        "grid_deg": GRID_RESOLUTION_DEG_SENSITIVITY,
        "baseline_start": BASELINE_YEAR_START,
        "baseline_end": BASELINE_YEAR_END,
        "elevated_quantile": 0.75,
        "grid_convention": GRID_CONVENTION_PRIMARY,
    },
    "modis_strict_threshold": {
        "sensor": SENSOR_MODIS,
        "grid_deg": GRID_RESOLUTION_DEG_PRIMARY,
        "baseline_start": BASELINE_YEAR_START,
        "baseline_end": BASELINE_YEAR_END,
        "elevated_quantile": 0.90,
        "grid_convention": GRID_CONVENTION_PRIMARY,
    },
    # Added in registry version 2 (approved before any real-data run).
    # VIIRS counterpart of modis_coarse_grid, so the grid-resolution
    # sensitivity is tested for both sensors and VIIRS evidence no longer
    # rests on a single configuration.
    "viirs_coarse_grid": {
        "sensor": SENSOR_VIIRS,
        "grid_deg": GRID_RESOLUTION_DEG_SENSITIVITY,
        "baseline_start": BASELINE_YEAR_START,
        "baseline_end": BASELINE_YEAR_END,
        "elevated_quantile": 0.75,
        "grid_convention": GRID_CONVENTION_PRIMARY,
    },
}

# Registry version: increment whenever a configuration is added, removed or
# changed.  Each change must be approved before real-data analysis.
#   1: primary, viirs_primary_grid, modis_coarse_grid, modis_strict_threshold
#   2: + viirs_coarse_grid (VIIRS, 0.5°, q=0.75)
RELIABILITY_CONFIG_REGISTRY_VERSION = 2
RELIABILITY_CONFIG_REGISTRY_HISTORY = {
    1: ["primary", "viirs_primary_grid", "modis_coarse_grid", "modis_strict_threshold"],
    2: ["primary", "viirs_primary_grid", "modis_coarse_grid", "modis_strict_threshold",
        "viirs_coarse_grid"],
}

# ---------------------------------------------------------------------------
# Reliability classification labels (Blueprint §3.4)
# ---------------------------------------------------------------------------
LABEL_CONSISTENTLY_ELEVATED  = "consistently_elevated"
LABEL_CLASSIFICATION_SENSITIVE = "classification_sensitive"
LABEL_INSUFFICIENT_EVIDENCE   = "insufficient_evidence"
LABEL_NOT_ELEVATED            = "not_elevated"

# Cross-sensor requirement not met: enough evaluable configurations overall, but
# at least one required sensor has no evaluable configuration.
LABEL_INSUFFICIENT_CROSS_SENSOR = "insufficient_cross_sensor_evidence"

# Sensor-specific finding labels (describe ONE sensor only; never cross-sensor
# agreement).  Deliberately different strings from the cross-sensor labels.
SENSOR_LABEL_ELEVATED     = "elevated"
SENSOR_LABEL_NOT_ELEVATED = "not_elevated"
SENSOR_LABEL_MIXED        = "mixed"
SENSOR_LABEL_INSUFFICIENT = "insufficient_evidence"

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
from pathlib import Path

PROJECT_ROOT   = Path(__file__).parent.parent
DATA_RAW       = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
DATA_MANIFESTS = PROJECT_ROOT / "data" / "manifests"
DATA_FIXTURES  = PROJECT_ROOT / "data" / "fixtures"
FRONTEND_DATA  = PROJECT_ROOT / "web" / "public" / "data"

# Ensure output directories exist at import time
for _p in (DATA_PROCESSED, DATA_MANIFESTS, DATA_FIXTURES, FRONTEND_DATA):
    _p.mkdir(parents=True, exist_ok=True)
