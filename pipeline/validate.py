"""
FireChronicle — schema and data-quality validation.

Validates raw NASA FIRMS DataFrames before any transformation.
Returns a ValidationResult that callers must check; this module
never silently drops or patches records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Set

import pandas as pd

from pipeline.config import (
    MODIS_CONFIDENCE_MIN_INT,
    MODIS_REQUIRED_COLUMNS,
    VIIRS_CONFIDENCE_KEEP,
    VIIRS_REQUIRED_COLUMNS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    BBOX,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Coordinate bounds — slightly wider than BBOX to allow for floating-point
# imprecision at the clip boundary.  Hard geographic limits enforce sanity.
# ---------------------------------------------------------------------------
LON_HARD_MIN, LON_HARD_MAX = -180.0, 180.0
LAT_HARD_MIN, LAT_HARD_MAX = -90.0, 90.0


@dataclass
class ValidationResult:
    """Outcome of a single validation pass."""
    sensor: str
    source_file: str
    total_rows: int
    missing_columns: List[str] = field(default_factory=list)
    malformed_coordinates: int = 0
    malformed_timestamps: int = 0
    out_of_bbox: int = 0
    duplicate_rows: int = 0
    low_confidence_rows: int = 0
    rows_accepted: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True when no blocking errors were found."""
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Sensor          : {self.sensor}",
            f"File            : {self.source_file}",
            f"Total rows      : {self.total_rows:,}",
            f"Accepted rows   : {self.rows_accepted:,}",
            f"Missing columns : {self.missing_columns}",
            f"Bad coordinates : {self.malformed_coordinates:,}",
            f"Bad timestamps  : {self.malformed_timestamps:,}",
            f"Outside bbox    : {self.out_of_bbox:,}",
            f"Duplicates      : {self.duplicate_rows:,}",
            f"Low confidence  : {self.low_confidence_rows:,}",
        ]
        if self.errors:
            lines.append(f"ERRORS ({len(self.errors)}): " + " | ".join(self.errors))
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}): " + " | ".join(self.warnings))
        return "\n".join(lines)


def _required_columns(sensor: str) -> Set[str]:
    if sensor == SENSOR_MODIS:
        return MODIS_REQUIRED_COLUMNS
    if sensor == SENSOR_VIIRS:
        return VIIRS_REQUIRED_COLUMNS
    raise ValueError(f"Unknown sensor: {sensor!r}")


def _validate_product_identity(
    df: pd.DataFrame,
    sensor: str,
    source_type: str,
    result: ValidationResult,
) -> None:
    """Check declared platform and processing status without rewriting values."""
    satellites = df["satellite"].fillna("").astype(str).str.strip().str.lower()
    satellite_values = set(satellites[satellites.ne("")])
    allowed_satellites = (
        {"terra", "aqua", "t", "a"}
        if sensor == SENSOR_MODIS
        else {"n20", "noaa-20", "j1", "jpss-1"}
    )
    if (
        satellites.eq("").any()
        or not satellite_values
        or not satellite_values.issubset(allowed_satellites)
    ):
        result.errors.append(
            f"Unexpected {sensor} satellite identifiers: {sorted(satellite_values)}"
        )

    if "instrument" in df.columns:
        instruments = df["instrument"].fillna("").astype(str).str.strip().str.lower()
        instrument_values = instruments
        instrument_values = set(instrument_values[instrument_values.ne("")])
        expected_instrument = "modis" if sensor == SENSOR_MODIS else "viirs"
        if (
            instruments.eq("").any()
            or not instrument_values
            or instrument_values != {expected_instrument}
        ):
            result.errors.append(
                f"Unexpected {sensor} instrument identifiers: {sorted(instrument_values)}"
            )

    if source_type not in {"archive", "nrt", "unspecified"}:
        result.errors.append(f"Unknown source processing status: {source_type!r}")
        return

    versions = df["version"].fillna("").astype(str).str.strip().str.lower()
    if versions.eq("").any():
        result.errors.append("Rows with missing product version identifiers")
    if source_type == "nrt" and not versions.str.endswith("nrt").all():
        result.errors.append("NRT source contains versions without an NRT suffix")
    elif source_type == "archive" and versions.str.endswith("nrt").any():
        result.errors.append("Archive source contains NRT product versions")


def validate_raw(
    df: pd.DataFrame,
    sensor: str,
    source_file: str = "<unknown>",
    source_type: str = "unspecified",
) -> ValidationResult:
    """
    Validate a raw FIRMS DataFrame.

    Parameters
    ----------
    df          : Raw DataFrame as loaded from a FIRMS CSV.
    sensor      : One of SENSOR_MODIS or SENSOR_VIIRS.
    source_file : Path or identifier for provenance logging.

    Returns
    -------
    ValidationResult
        Callers must check `.is_valid` before proceeding.
        Rows are *not* filtered here; filtering happens in normalize.py.
    """
    result = ValidationResult(
        sensor=sensor,
        source_file=source_file,
        total_rows=len(df),
    )

    # 1 — Column presence
    required = _required_columns(sensor)
    present  = set(df.columns.str.lower())
    missing  = sorted(required - present)
    if missing:
        result.missing_columns = missing
        result.errors.append(f"Missing required columns: {missing}")
        logger.error("validate_raw: %s missing columns %s", source_file, missing)
        return result  # cannot proceed without required columns

    # Normalise column names to lower-case for all subsequent checks
    df = df.copy()
    df.columns = df.columns.str.lower()

    _validate_product_identity(df, sensor, source_type, result)

    # 2 — Coordinate sanity (hard geographic bounds, not bbox)
    # Raw CSV data arrives as str; cast to numeric before comparing.
    lat_num = pd.to_numeric(df["latitude"],  errors="coerce")
    lon_num = pd.to_numeric(df["longitude"], errors="coerce")
    bad_lat = lat_num.isna() | (lat_num < LAT_HARD_MIN) | (lat_num > LAT_HARD_MAX)
    bad_lon = lon_num.isna() | (lon_num < LON_HARD_MIN) | (lon_num > LON_HARD_MAX)
    bad_coords = bad_lat | bad_lon
    result.malformed_coordinates = int(bad_coords.sum())
    if result.malformed_coordinates > 0:
        result.warnings.append(
            f"{result.malformed_coordinates} rows have invalid coordinates and will be excluded"
        )

    # 3 — Timestamp parseability
    combined_dt = df["acq_date"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4)
    try:
        parsed = pd.to_datetime(combined_dt, format="%Y-%m-%d %H%M", errors="coerce")
    except Exception:
        parsed = pd.to_datetime(combined_dt, errors="coerce")
    bad_ts = parsed.isna()
    result.malformed_timestamps = int(bad_ts.sum())
    if result.malformed_timestamps > 0:
        result.warnings.append(
            f"{result.malformed_timestamps} rows have unparseable timestamps and will be excluded"
        )

    # 4 — Spatial coverage relative to target BBOX
    # Use the already-cast numeric series from step 2.
    lon_min, lat_min, lon_max, lat_max = BBOX
    out_of_bbox = (
        (lon_num < lon_min) | (lon_num > lon_max) |
        (lat_num < lat_min) | (lat_num > lat_max)
    ) & ~bad_coords
    result.out_of_bbox = int(out_of_bbox.sum())
    if result.out_of_bbox == len(df):
        result.errors.append(
            "All rows fall outside the target bounding box — confirm the correct region was downloaded"
        )
        logger.error("validate_raw: %s — 0 rows in bbox", source_file)

    # 5 — Duplicate detection (exact latitude/longitude/acq_date/acq_time tuples)
    dup_mask = df.duplicated(subset=["latitude", "longitude", "acq_date", "acq_time"], keep="first")
    result.duplicate_rows = int(dup_mask.sum())
    if result.duplicate_rows > 0:
        result.warnings.append(
            f"{result.duplicate_rows} duplicate rows detected (kept first occurrence)"
        )

    # 6 — Confidence coverage (count only; exclusion happens in normalize.py)
    conf_col = "confidence"
    if conf_col in df.columns:
        if sensor == SENSOR_MODIS:
            # MODIS: integer 0–100; low = < MODIS_CONFIDENCE_MIN_INT
            conf_num = pd.to_numeric(df[conf_col], errors="coerce")
            if conf_num.notna().any():
                low_mask = conf_num.isna() | (conf_num < MODIS_CONFIDENCE_MIN_INT)
            else:
                # Fallback string labels
                low_mask = df[conf_col].astype(str).str.lower().isin({"l", "low"})
        else:
            # VIIRS: string labels
            low_mask = df[conf_col].astype(str).str.lower().isin({"l", "low"})
        result.low_confidence_rows = int(low_mask.sum())
        if result.low_confidence_rows > 0:
            result.warnings.append(
                f"{result.low_confidence_rows} low-confidence rows present (will be excluded in normalize)"
            )

    # Estimate accepted rows.
    # This is an approximation: excludes bad coords and bad timestamps only.
    # Low-confidence, bbox, and duplicate exclusions happen in normalize.py.
    # The manifest records this as an upper bound, not the final accepted count.
    exclude = bad_coords | bad_ts
    result.rows_accepted = int((~exclude).sum())
    result.warnings.append(
        "rows_accepted is an upper-bound estimate; "
        "low-confidence and duplicate rows are excluded in normalize.py"
    )

    logger.info("validate_raw result:\n%s", result.summary())
    return result
