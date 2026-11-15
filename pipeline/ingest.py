"""
FireChronicle — raw data ingestion and manifest recording.

Responsibilities
----------------
1. Discover NASA FIRMS CSV files in data/raw/{modis,viirs}/.
2. Load each file, run validation, and record a provenance manifest.
3. Return clean DataFrames ready for normalize.py.

This module does NOT download data — that is handled by scripts/download.py.
If raw files are absent it returns an empty result with a clear diagnostic.

Manifest format (data/manifests/<sensor>_manifest.json)
--------------------------------------------------------
{
  "manifest_version": 2,
  "processing_version": "...",
  "generated_at": "ISO-8601 UTC",
  "sensor": "...",
  "files": [
    {
      "filename": "...",
      "path": "data/raw/<sensor>/... (repository-relative, POSIX separators)",
      "source_type": "archive | nrt | unspecified",
      "request_id": "...",
      "product_code": "...",
      "sha256": "...",
      "rows_raw": N,
      "rows_accepted": N,
      "validation_metrics": {},
      "date_min": "YYYY-MM-DD",
      "date_max": "YYYY-MM-DD",
      "bbox_actual": [lon_min, lat_min, lon_max, lat_max],
      "validation_errors": [],
      "validation_warnings": []
    }
  ]
}
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from pipeline.config import (
    DATA_MANIFESTS,
    DATA_RAW,
    PROCESSING_VERSION,
    PROJECT_ROOT,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.validate import validate_raw

logger = logging.getLogger(__name__)

SENSOR_DIRS: Dict[str, Path] = {
    SENSOR_MODIS: DATA_RAW / "modis",
    SENSOR_VIIRS: DATA_RAW / "viirs",
}

# Canonical repository-relative location of each sensor's raw files.
# Manifest paths are always recorded under this prefix, in POSIX form, so a
# manifest never contains a machine-specific absolute path and stays valid
# when the repository is cloned into a different directory.
SENSOR_REPO_DIRS: Dict[str, str] = {
    SENSOR_MODIS: "data/raw/modis",
    SENSOR_VIIRS: "data/raw/viirs",
}


def portable_source_path(path: Path, sensor_dir: Path, sensor: str) -> str:
    """Return the repository-relative POSIX path recorded for a raw source file.

    The path is built from the file's location inside its sensor directory,
    e.g. ``data/raw/modis/archive/fire_archive_M-C61_849850.csv``.
    """
    relative = path.relative_to(sensor_dir).as_posix()
    return f"{SENSOR_REPO_DIRS[sensor]}/{relative}"


def _check_recorded_path_syntax(recorded_path: str) -> list[str]:
    """Validate the stored form of a manifest path and return its segments.

    The stored form is the one written by ``portable_source_path``:
    repository-relative, ``/``-separated, with no empty, ``.`` or ``..``
    segments. It is checked as text so the result is the same on every OS.
    """
    if not isinstance(recorded_path, str) or not recorded_path:
        raise ValueError(f"Manifest path must be a non-empty string: {recorded_path!r}")
    if "\\" in recorded_path:
        raise ValueError(f"Manifest path must use '/' separators only: {recorded_path!r}")
    if ":" in recorded_path:
        # Drive letters (C:/x, C:x), URLs (file:...) and NTFS stream syntax.
        raise ValueError(f"Manifest path must not contain ':' or a drive prefix: {recorded_path!r}")
    if recorded_path.startswith("/"):
        raise ValueError(f"Manifest path must be repository-relative: {recorded_path!r}")
    if any(ord(ch) < 32 for ch in recorded_path):
        raise ValueError(f"Manifest path must not contain control characters: {recorded_path!r}")
    segments = recorded_path.split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        raise ValueError(
            f"Manifest path must not contain empty, '.' or '..' segments: {recorded_path!r}"
        )
    return segments


def resolve_manifest_path(
    recorded_path: str,
    project_root: Path = PROJECT_ROOT,
    *,
    require_file: bool = False,
) -> Path:
    """Resolve a manifest ``path`` value against a repository root.

    Raises ``ValueError`` if the stored path is not a clean repository-relative
    ``/`` path, if it resolves outside ``project_root`` (including through
    symlinks or junctions), or if it names an existing directory. With
    ``require_file=True`` the target must also exist as a regular file.

    The returned path is ``project_root`` joined with the stored segments, so
    a manifest stays valid wherever the repository is cloned.
    """
    segments = _check_recorded_path_syntax(recorded_path)
    root = Path(project_root)
    target = root.joinpath(*segments)

    real_root = root.resolve()
    real_target = target.resolve()
    if not real_target.is_relative_to(real_root):
        raise ValueError(
            f"Manifest path resolves outside the repository: {recorded_path!r}"
        )
    if real_target.is_dir():
        raise ValueError(f"Manifest path names a directory, not a file: {recorded_path!r}")
    if require_file and not real_target.is_file():
        raise ValueError(f"Manifest source file not found: {recorded_path!r}")
    return target

EXPECTED_PRODUCT_CODES = {
    SENSOR_MODIS: "M-C61",
    SENSOR_VIIRS: "J1V-C2",
}


def _load_csv(path: Path) -> pd.DataFrame:
    """Load a FIRMS CSV with robust encoding and type handling."""
    df = pd.read_csv(
        path,
        low_memory=False,
        encoding="utf-8",
        na_values=["", "NA", "N/A", "nan", "NaN", "none", "None"],
        dtype=str,          # read all as str first; types applied after validation
    )
    df.columns = df.columns.str.lower().str.strip()
    return df


def _source_metadata(path: Path, sensor_dir: Path, sensor: str) -> dict:
    """Identify NASA download provenance from its preserved folder and filename."""
    relative_parts = {part.lower() for part in path.relative_to(sensor_dir).parts[:-1]}
    folder_statuses = relative_parts & {"archive", "nrt"}

    match = re.match(
        r"^fire_(archive|nrt)_([a-z0-9-]+)_(\d+)\.csv$",
        path.name,
        flags=re.IGNORECASE,
    )
    filename_status = match.group(1).lower() if match else None
    statuses = folder_statuses | ({filename_status} if filename_status else set())
    errors = []
    if len(statuses) > 1:
        errors.append(
            f"Conflicting archive/NRT indicators in path and filename: {sorted(statuses)}"
        )

    source_type = next(iter(statuses)) if len(statuses) == 1 else "unspecified"
    product_code = match.group(2).upper() if match else None
    request_id = match.group(3) if match else None
    expected_product = EXPECTED_PRODUCT_CODES[sensor]
    if product_code and product_code != expected_product:
        errors.append(
            f"Filename product code {product_code!r} does not match {sensor} "
            f"({expected_product})"
        )

    return {
        "source_type": source_type,
        "product_code": product_code,
        "request_id": request_id,
        "metadata_errors": errors,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distinct_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    return sorted(value for value in values.unique() if value)


def _file_manifest_entry(
    path: Path,
    df_raw: pd.DataFrame,
    result,
    source: dict,
    sha256: str,
    recorded_path: str,
) -> dict:
    """Build a single manifest entry for one ingested file."""
    # Determine actual date coverage from successfully parsed rows
    date_min = date_max = None
    if "acq_date" in df_raw.columns:
        dates = pd.to_datetime(df_raw["acq_date"], errors="coerce").dropna()
        if not dates.empty:
            date_min = dates.min().strftime("%Y-%m-%d")
            date_max = dates.max().strftime("%Y-%m-%d")

    # Actual coordinate bounding box of this file
    bbox_actual = None
    if "longitude" in df_raw.columns and "latitude" in df_raw.columns:
        lons = pd.to_numeric(df_raw["longitude"], errors="coerce").dropna()
        lats = pd.to_numeric(df_raw["latitude"],  errors="coerce").dropna()
        if not lons.empty and not lats.empty:
            bbox_actual = [
                round(float(lons.min()), 6),
                round(float(lats.min()), 6),
                round(float(lons.max()), 6),
                round(float(lats.max()), 6),
            ]
    return {
        "filename": path.name,
        "path": recorded_path,
        "source_type": source["source_type"],
        "product_code": source["product_code"],
        "request_id": source["request_id"],
        "sha256": sha256,
        "satellite_values": _distinct_values(df_raw, "satellite"),
        "instrument_values": _distinct_values(df_raw, "instrument"),
        "product_versions": _distinct_values(df_raw, "version"),
        "rows_raw": result.total_rows,
        "rows_accepted": result.rows_accepted,
        "validation_metrics": {
            "malformed_coordinates": result.malformed_coordinates,
            "malformed_timestamps": result.malformed_timestamps,
            "out_of_bbox": result.out_of_bbox,
            "duplicate_rows": result.duplicate_rows,
            "low_confidence_rows": result.low_confidence_rows,
        },
        "date_min": date_min,
        "date_max": date_max,
        "bbox_actual": bbox_actual,
        "validation_errors": result.errors,
        "validation_warnings": result.warnings,
    }


def _acquisition_dates(df_raw: pd.DataFrame) -> set[str]:
    if "acq_date" not in df_raw.columns:
        return set()
    dates = pd.to_datetime(df_raw["acq_date"], errors="coerce").dropna()
    return set(dates.dt.strftime("%Y-%m-%d"))


def ingest_sensor(sensor: str) -> Tuple[Optional[pd.DataFrame], dict]:
    """
    Load and validate all CSV files for one sensor.

    Parameters
    ----------
    sensor : SENSOR_MODIS or SENSOR_VIIRS

    Returns
    -------
    df      : Combined raw DataFrame (None if no valid files found)
    manifest: Provenance dict (always returned, even on failure)
    """
    sensor_dir = SENSOR_DIRS.get(sensor)
    if sensor_dir is None:
        raise ValueError(f"Unknown sensor: {sensor!r}")

    manifest: dict = {
        "manifest_version": 2,
        "processing_version": PROCESSING_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sensor": sensor,
        "files": [],
    }

    csv_files = sorted(sensor_dir.rglob("*.csv"))
    if not csv_files:
        logger.warning("ingest_sensor: no CSV files found in %s", sensor_dir)
        manifest["warning"] = f"No CSV files found in {SENSOR_REPO_DIRS[sensor]}"
        return None, manifest

    loaded_files: list[dict] = []
    for csv_path in csv_files:
        source = _source_metadata(csv_path, sensor_dir, sensor)
        recorded_path = portable_source_path(csv_path, sensor_dir, sensor)
        logger.info("Loading %s", csv_path)
        try:
            df_raw = _load_csv(csv_path)
        except Exception as exc:
            logger.error("Failed to read %s: %s", csv_path, exc)
            manifest["files"].append({
                "filename": csv_path.name,
                "path": recorded_path,
                "source_type": source["source_type"],
                "product_code": source["product_code"],
                "request_id": source["request_id"],
                "sha256": _sha256(csv_path),
                "rows_raw": 0,
                "rows_accepted": 0,
                "validation_errors": source["metadata_errors"] + [
                    "Read error: " + str(exc).replace(str(csv_path), recorded_path)
                ],
                "validation_warnings": [],
            })
            continue

        result = validate_raw(
            df_raw,
            sensor,
            source_file=recorded_path,
            source_type=source["source_type"],
        )
        result.errors.extend(source["metadata_errors"])
        entry = _file_manifest_entry(
            csv_path, df_raw, result, source=source, sha256=_sha256(csv_path),
            recorded_path=recorded_path,
        )
        manifest["files"].append(entry)
        loaded_files.append({
            "path": csv_path,
            "recorded_path": recorded_path,
            "data": df_raw,
            "result": result,
            "source": source,
            "manifest_entry": entry,
            "dates": _acquisition_dates(df_raw),
        })

    archive_dates = set().union(*(
        item["dates"] for item in loaded_files
        if item["source"]["source_type"] == "archive"
    ))
    nrt_dates = set().union(*(
        item["dates"] for item in loaded_files
        if item["source"]["source_type"] == "nrt"
    ))
    overlapping_dates = sorted(archive_dates & nrt_dates)
    if overlapping_dates:
        overlap_message = (
            "Archive and NRT acquisitions overlap on "
            f"{len(overlapping_dates)} date(s); resolve archive replacement before ingestion"
        )
        manifest["blocking_errors"] = [overlap_message]
        manifest["overlapping_archive_nrt_dates"] = overlapping_dates
        for item in loaded_files:
            item["result"].errors.append(overlap_message)

    frames: List[pd.DataFrame] = []
    for item in loaded_files:
        if not item["result"].is_valid:
            logger.error("Validation failed for %s — skipping", item["path"].name)
            continue

        # Keep source lineage attached through normalization and analysis.
        df_raw = item["data"].copy()
        source = item["source"]
        df_raw["_source_file"] = item["path"].name
        df_raw["_source_path"] = item["recorded_path"]
        df_raw["_source_type"] = source["source_type"]
        df_raw["_request_id"] = source["request_id"]
        df_raw["_product_code"] = source["product_code"]
        df_raw["_source_sha256"] = item["manifest_entry"]["sha256"]
        df_raw["_sensor"] = sensor
        frames.append(df_raw)

    # Write manifest to disk
    manifest_path = DATA_MANIFESTS / f"{sensor}_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    logger.info("Manifest written to %s", manifest_path)

    if not frames:
        return None, manifest

    combined = pd.concat(frames, ignore_index=True)
    logger.info(
        "ingest_sensor: %s — %d total rows from %d file(s)",
        sensor, len(combined), len(frames),
    )
    return combined, manifest


def ingest_all() -> Dict[str, Optional[pd.DataFrame]]:
    """
    Ingest MODIS and VIIRS in one call.

    Returns
    -------
    Dict mapping sensor identifier to DataFrame (or None if unavailable).
    """
    results = {}
    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        df, _manifest = ingest_sensor(sensor)
        results[sensor] = df
        if df is None:
            logger.warning("No valid data loaded for sensor %s", sensor)
        else:
            logger.info("Sensor %s: %d rows ingested", sensor, len(df))
    return results
