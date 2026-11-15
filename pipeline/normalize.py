"""
FireChronicle — normalization and standardisation.

Takes raw validated DataFrames from ingest.py and produces a clean,
typed, sensor-tagged DataFrame with:
- UTC acquisition datetime
- float64 latitude/longitude
- sensor product identifier
- confidence quality flag (accepted/excluded)
- fire radiative power (FRP)
- daynight indicator

Records excluded at this stage are logged with counts but NOT silently dropped.
The returned DataFrame contains only accepted rows; callers receive the
exclusion counts separately for provenance reporting.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.config import (
    MODIS_CONFIDENCE_MIN_INT,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    VIIRS_CONFIDENCE_KEEP,
    YEAR_END,
    YEAR_START,
)

logger = logging.getLogger(__name__)

EXPECTED_YEAR_RANGE = range(YEAR_START, YEAR_END + 1)


@dataclass
class NormalizationStats:
    sensor: str
    rows_in: int
    excluded_bad_coords: int = 0
    excluded_bad_timestamp: int = 0
    excluded_outside_years: int = 0
    excluded_low_confidence: int = 0
    excluded_duplicates: int = 0
    rows_out: int = 0

    def report(self) -> str:
        total_excluded = (
            self.excluded_bad_coords
            + self.excluded_bad_timestamp
            + self.excluded_outside_years
            + self.excluded_low_confidence
            + self.excluded_duplicates
        )
        return (
            f"[{self.sensor}] normalize: "
            f"in={self.rows_in:,} "
            f"bad_coords={self.excluded_bad_coords:,} "
            f"bad_ts={self.excluded_bad_timestamp:,} "
            f"outside_years={self.excluded_outside_years:,} "
            f"low_conf={self.excluded_low_confidence:,} "
            f"dupes={self.excluded_duplicates:,} "
            f"out={self.rows_out:,} "
            f"total_excluded={total_excluded:,}"
        )


def normalize(
    df: pd.DataFrame,
    sensor: str,
    year_range: Optional[range] = None,
) -> tuple[pd.DataFrame, NormalizationStats]:
    """
    Normalize a raw FIRMS DataFrame for one sensor.

    Parameters
    ----------
    df     : Raw string-typed DataFrame from ingest.py
    sensor : SENSOR_MODIS or SENSOR_VIIRS
    year_range : Years to keep. Defaults to the configured analysis window
                 (2019–2024). Only the recent-activity assessment passes a
                 wider range; the historical analysis always uses the default.

    Returns
    -------
    clean_df : Typed, filtered DataFrame ready for aggregate.py
    stats    : Row-level exclusion counts for provenance
    """
    stats = NormalizationStats(sensor=sensor, rows_in=len(df))
    df = df.copy()
    df.columns = df.columns.str.lower().str.strip()

    # -----------------------------------------------------------------------
    # 1. Coordinates — cast to float, exclude bad values
    # -----------------------------------------------------------------------
    df["latitude"]  = pd.to_numeric(df["latitude"],  errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    bad_coords = df["latitude"].isna() | df["longitude"].isna()
    stats.excluded_bad_coords = int(bad_coords.sum())
    df = df[~bad_coords].copy()

    # -----------------------------------------------------------------------
    # 2. UTC acquisition datetime
    # FIRMS CSVs: acq_date = YYYY-MM-DD, acq_time = HHMM (integer or zero-padded str)
    # -----------------------------------------------------------------------
    time_str = df["acq_date"].astype(str) + " " + df["acq_time"].astype(str).str.zfill(4)
    df["acq_datetime_utc"] = pd.to_datetime(time_str, format="%Y-%m-%d %H%M", errors="coerce")
    bad_ts = df["acq_datetime_utc"].isna()
    stats.excluded_bad_timestamp = int(bad_ts.sum())
    df = df[~bad_ts].copy()

    df["year"]  = df["acq_datetime_utc"].dt.year
    df["month"] = df["acq_datetime_utc"].dt.month

    # -----------------------------------------------------------------------
    # 3. Restrict to configured year window
    # -----------------------------------------------------------------------
    outside_years = ~df["year"].isin(EXPECTED_YEAR_RANGE if year_range is None else year_range)
    stats.excluded_outside_years = int(outside_years.sum())
    df = df[~outside_years].copy()

    # -----------------------------------------------------------------------
    # 4. Confidence / quality filter
    #
    # MODIS: confidence is an integer 0–100.  Keep >= MODIS_CONFIDENCE_MIN_INT
    #   (i.e. nominal ≥ 30 and high ≥ 80).  Low-confidence < 30 is excluded.
    #
    # VIIRS: confidence is a string ("low" / "nominal" / "high").
    #   Keep values in VIIRS_CONFIDENCE_KEEP; exclude "low".
    #
    # If the confidence column is absent, log a warning and skip filtering
    # rather than silently accepting all rows.
    # -----------------------------------------------------------------------
    if "confidence" in df.columns:
        if sensor == SENSOR_MODIS:
            # Try numeric interpretation first (integer CSVs from FIRMS archive)
            conf_num = pd.to_numeric(df["confidence"], errors="coerce")
            if conf_num.notna().any():
                # Numeric confidence: exclude NaN and values < threshold
                low_conf = conf_num.isna() | (conf_num < MODIS_CONFIDENCE_MIN_INT)
            else:
                # Fallback: some NRT files may use string labels
                conf_str = df["confidence"].astype(str).str.lower().str.strip()
                # Map string labels to pass/fail (nominal/high pass, low fails)
                low_conf = conf_str.isin({"low", "l"}) | (
                    ~conf_str.isin({"nominal", "high", "n", "h"}) & conf_num.isna()
                )
        else:
            # VIIRS: string confidence
            conf_norm = df["confidence"].astype(str).str.lower().str.strip()
            low_conf  = ~conf_norm.isin(VIIRS_CONFIDENCE_KEEP)
        stats.excluded_low_confidence = int(low_conf.sum())
        df = df[~low_conf].copy()
    else:
        logger.warning("No 'confidence' column found for %s; skipping confidence filter", sensor)

    # -----------------------------------------------------------------------
    # 5. Deduplicate on spatial/temporal key
    # -----------------------------------------------------------------------
    dup_mask = df.duplicated(
        subset=["latitude", "longitude", "acq_datetime_utc"], keep="first"
    )
    stats.excluded_duplicates = int(dup_mask.sum())
    df = df[~dup_mask].copy()

    # -----------------------------------------------------------------------
    # 6. Cast remaining numeric columns
    # -----------------------------------------------------------------------
    df["frp"] = pd.to_numeric(df.get("frp"), errors="coerce")

    # Keep MODIS channel-21/22 brightness sensor-specific.  The downloaded
    # VIIRS export's brightness columns have no verified I4/I5 mapping.
    if sensor == SENSOR_MODIS:
        df["brightness"] = pd.to_numeric(df.get("brightness"), errors="coerce")

    # -----------------------------------------------------------------------
    # 7. Standardise sensor tag, daynight and product version
    # -----------------------------------------------------------------------
    df["sensor"]  = sensor
    df["daynight"] = df.get("daynight", pd.Series(["U"] * len(df), index=df.index))
    df["product_version"] = df.get("version", pd.Series([None] * len(df), index=df.index))

    # -----------------------------------------------------------------------
    # 8. Select and return canonical columns
    # -----------------------------------------------------------------------
    output_cols = [
        "latitude", "longitude",
        "acq_datetime_utc", "year", "month",
        "sensor", "satellite", "instrument", "daynight", "product_version",
        "frp",
        "_source_file", "_source_path", "_source_type",
        "_request_id", "_product_code", "_source_sha256",
    ]
    if sensor == SENSOR_MODIS:
        output_cols.insert(output_cols.index("frp"), "brightness")
    # Keep only columns that exist
    output_cols = [c for c in output_cols if c in df.columns]
    df = df[output_cols].reset_index(drop=True)

    stats.rows_out = len(df)
    logger.info(stats.report())
    return df, stats


def normalize_all(
    raw_data: dict[str, Optional[pd.DataFrame]],
) -> dict[str, Optional[tuple[pd.DataFrame, NormalizationStats]]]:
    """
    Normalize all sensors.

    Parameters
    ----------
    raw_data : Dict from ingest.ingest_all()

    Returns
    -------
    Dict mapping sensor -> (clean_df, stats) or None if no raw data.
    """
    results = {}
    for sensor, df in raw_data.items():
        if df is None:
            results[sensor] = None
            continue
        clean_df, stats = normalize(df, sensor)
        results[sensor] = (clean_df, stats)
    return results
