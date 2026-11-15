"""
FireChronicle — versioned JSON export for the React frontend.

Produces the five contracted JSON files in web/public/data/:
  regions.json      — region geometry and metadata
  calendar.json     — monthly activity calendar (sensor-specific)
  sensors.json      — sensor comparison and overlap diagnostics
  reliability.json  — stability labels per period
  methodology.json  — processing assumptions and limitations

Schema version is embedded in every file. Null means unavailable or
not evaluated; it NEVER represents a fabricated zero.

This module must be called after all pipeline stages have run.  It is the
only module that writes to the frontend data directory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd

from pipeline.config import (
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    BBOX,
    DATA_MANIFESTS,
    FRONTEND_DATA,
    GRID_CONVENTION_PRIMARY,
    GRID_CONVENTION_SENSITIVITY,
    GRID_RESOLUTION_DEG_PRIMARY,
    GRID_RESOLUTION_DEG_SENSITIVITY,
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_CROSS_SENSOR,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    PROCESSING_VERSION,
    REGION_ID,
    REGION_NAME,
    RELIABILITY_CONFIGS,
    RELIABILITY_CONFIG_REGISTRY_HISTORY,
    RELIABILITY_CONFIG_REGISTRY_VERSION,
    RELIABILITY_MIN_EVALUABLE_CONFIGS,
    RELIABILITY_MIN_EVALUABLE_PER_SENSOR,
    RELIABILITY_REQUIRED_SENSORS,
    SENSOR_LABELS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    YEAR_END,
    YEAR_START,
)

from pipeline.aggregate import grid_cell_counts, grid_geographic_support

METRIC_DEFINITIONS = {
    'B': {
        'role': 'primary',
        'field': 'occupied_cell_fraction',
        'eligible_cells': 'every grid cell intersecting the bounding box',
        'in_bounds_detections': 'all included',
    },
    'A': {
        'role': 'sensitivity',
        'field': 'occupied_cell_fraction_convention_a',
        'eligible_cells': 'grid cells whose lower-left origin lies inside the bounding box',
        'in_bounds_detections': 'detections in the uncovered boundary strip excluded from the fraction',
    },
}
AREA_CAVEAT = (
    'occupied_cell_fraction counts grid cells (each eligible cell has weight 1, including '
    'boundary cells that extend outside the bounding box). It is not area-weighted and is '
    'not a burned-area, fire-count or severity measurement.'
)

logger = logging.getLogger(__name__)

# 1.1.0 (additive): grid_convention + boundary fields, Convention A sensitivity
# values in calendar.json, cross-sensor fields and the new stability label
# "insufficient_cross_sensor_evidence" in reliability.json.  No field removed.
# 1.2.0 (additive): config_registry_version / config_registry_history fields.
CONTRACT_VERSION = "1.2.0"
FIXTURE_WARNING = "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT"


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalars and NaN → null."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return None if np.isnan(obj) else float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (pd.Timestamp,)):
            return obj.isoformat()
        return super().default(obj)

    def encode(self, obj: Any) -> str:
        return super().encode(obj)


def _write(filename: str, data: dict) -> None:
    path = FRONTEND_DATA / filename
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, cls=_NumpyEncoder, ensure_ascii=False)
    logger.info("Exported %s (%d bytes)", path, path.stat().st_size)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_manifest_details(
    sensor: str,
    is_fixture: bool,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    if is_fixture:
        return [], [], {}

    manifest_path = DATA_MANIFESTS / f"{sensor}_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Source manifest is required for real-data export: {manifest_path}")

    with manifest_path.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError(f"Invalid source manifest structure: {manifest_path}")

    files = manifest["files"]
    versions = sorted({
        version
        for entry in files
        if isinstance(entry, dict)
        for version in entry.get("product_versions", [])
        if isinstance(version, str)
    })
    source_types = sorted({
        entry["source_type"]
        for entry in files
        if isinstance(entry, dict) and entry.get("source_type") in {"archive", "nrt"}
    })
    versions_by_type: dict[str, list[str]] = {}
    for source_type in source_types:
        versions_by_type[source_type] = sorted({
            version
            for entry in files
            if isinstance(entry, dict) and entry.get("source_type") == source_type
            for version in entry.get("product_versions", [])
            if isinstance(version, str)
        })
    return versions, source_types, versions_by_type


def _modis_product_description(versions: list[str]) -> str:
    collections = []
    if "6.03" in versions:
        collections.append("6")
    if any(version == "61.03" or version.startswith("6.1") for version in versions):
        collections.append("6.1")
    if not collections:
        return "MODIS Active Fire"
    return f"MODIS Collection {' and '.join(collections)} Active Fire"


# ---------------------------------------------------------------------------
# regions.json
# ---------------------------------------------------------------------------
def export_regions(is_fixture: bool = False) -> None:
    """
    Export region geometry and metadata.

    Schema v1.0.0
    -------------
    {
      "contract_version": "1.0.0",
      "processing_version": "...",
      "generated_at": "ISO-8601",
      "regions": [
        {
          "region_id": "south_sumatra",
          "name": "South Sumatra, Indonesia",
          "bbox": [lon_min, lat_min, lon_max, lat_max],
          "supported_sensors": [...],
          "supported_years": [2019, ..., 2024],
          "notes": "..."
        }
      ]
    }
    """
    lon_min, lat_min, lon_max, lat_max = BBOX
    data = {
        "contract_version": CONTRACT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "generated_at": _now_utc(),
        "is_fixture": is_fixture,
        "fixture_warning": "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT" if is_fixture else None,
        "regions": [
            {
                "region_id": REGION_ID,
                "name": REGION_NAME,
                "bbox": [lon_min, lat_min, lon_max, lat_max],
                "supported_sensors": [SENSOR_MODIS, SENSOR_VIIRS],
                "supported_years": list(range(YEAR_START, YEAR_END + 1)),
                "grid_resolution_deg": GRID_RESOLUTION_DEG_PRIMARY,
                "notes": (
                    "South Sumatra pilot region. Bounding box from Engineering Blueprint §3.1. "
                    "Coverage subject to data availability; missing months are not confirmed zero activity."
                ),
            }
        ],
    }
    _write("regions.json", data)


# ---------------------------------------------------------------------------
# calendar.json
# ---------------------------------------------------------------------------
def export_calendar(
    agg_by_sensor: dict[str, Optional[pd.DataFrame]],
    anomaly_by_sensor: dict[str, Optional[pd.DataFrame]],
    is_fixture: bool = False,
    agg_a_by_sensor: Optional[dict[str, Optional[pd.DataFrame]]] = None,
) -> None:
    """
    Export the monthly activity calendar.

    Parameters
    ----------
    agg_by_sensor     : sensor -> aggregated DataFrame (from aggregate.py)
    anomaly_by_sensor : sensor -> anomaly-enriched DataFrame (from baseline.py)

    Schema v1.0.0
    -------------
    {
      "contract_version": "1.0.0",
      "region_id": "...",
      "baseline_window": {"start": 2019, "end": 2024},
      "missing_data_note": "...",
      "sensors": {
        "MODIS_C61": {
          "label": "...",
          "months": [
            {
              "period": "2019-01",
              "year": 2019,
              "month": 1,
              "detection_count": 42,
              "occupied_cell_fraction": 0.123,
              "has_data": true,
              "baseline_median": 0.100,
              "anomaly": 0.023,
              "is_elevated": false,
              "anomaly_label": "not_elevated"
            }, ...
          ]
        }
      }
    }
    Null values represent missing/unevaluated data, never fabricated zeros.
    """
    sensors_data: dict = {}

    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        _df_anomaly = anomaly_by_sensor.get(sensor)
        df = _df_anomaly if (_df_anomaly is not None) else agg_by_sensor.get(sensor)
        if df is None:
            sensors_data[sensor] = {
                "label": SENSOR_LABELS.get(sensor, sensor),
                "available": False,
                "months": [],
            }
            continue

        # Convention A sensitivity values, keyed by period
        sens_by_period: dict = {}
        df_a = (agg_a_by_sensor or {}).get(sensor)
        if df_a is not None:
            for _, ra in df_a.iterrows():
                sens_by_period[ra["period"]] = ra

        months = []
        for _, row in df.iterrows():
            ocf = row.get("occupied_cell_fraction")
            ra = sens_by_period.get(row["period"])
            months.append({
                "period": row["period"],
                "year":   int(row["year"]),
                "month":  int(row["month"]),
                "detection_count":        int(row.get("detection_count", 0)),
                "occupied_cell_fraction": None if pd.isna(ocf) else round(float(ocf), 6),
                "has_data":               bool(row.get("has_data", False)),
                "coverage_note":          str(row.get("coverage_note", "")),
                "baseline_median":        _safe_float(row.get("baseline_median")),
                "anomaly":                _safe_float(row.get("anomaly")),
                "is_elevated":            bool(row.get("is_elevated", False)),
                "anomaly_label":          str(row.get("anomaly_label", LABEL_INSUFFICIENT_EVIDENCE)),
                "elevated_threshold":     _safe_float(row.get("elevated_threshold")),
                "grid_convention":        str(row.get("grid_convention", GRID_CONVENTION_PRIMARY)),
                "occupied_cells":         int(row.get("occupied_cells", 0)),
                "total_eligible_cells":   int(row.get("total_eligible_cells", 0)),
                "partial_boundary_cells": int(row.get("partial_boundary_cells", 0)),
                "partial_cell_detections": int(row.get("partial_cell_detections", 0)),
                "occupied_cell_fraction_convention_a": (
                    None if ra is None else _safe_float(ra.get("occupied_cell_fraction"))
                ),
                "occupied_cells_convention_a": (
                    None if ra is None else int(ra.get("occupied_cells", 0))
                ),
            })

        sensors_data[sensor] = {
            "label": SENSOR_LABELS.get(sensor, sensor),
            "available": True,
            "months": months,
        }

    data = {
        "contract_version": CONTRACT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "generated_at": _now_utc(),
        "is_fixture": is_fixture,
        "fixture_warning": "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT" if is_fixture else None,
        "region_id": REGION_ID,
        "baseline_window": {"start": BASELINE_YEAR_START, "end": BASELINE_YEAR_END},
        "grid_resolution_deg": GRID_RESOLUTION_DEG_PRIMARY,
        "primary_grid_convention": GRID_CONVENTION_PRIMARY,
        "sensitivity_grid_convention": GRID_CONVENTION_SENSITIVITY,
        "metric_definitions": METRIC_DEFINITIONS,
        "grid_cells": {
            c: grid_cell_counts(resolution=GRID_RESOLUTION_DEG_PRIMARY, convention=c)
            for c in (GRID_CONVENTION_PRIMARY, GRID_CONVENTION_SENSITIVITY)
        },
        "area_caveat": AREA_CAVEAT,
        "missing_data_note": (
            "null values indicate no satellite detections after quality filtering, "
            "not confirmed zero fire activity. "
            "Short baseline (2019-2024, max 6 years per month) limits statistical confidence."
        ),
        "sensors": sensors_data,
    }
    _write("calendar.json", data)


# ---------------------------------------------------------------------------
# sensors.json
# ---------------------------------------------------------------------------
def export_sensors(
    agg_by_sensor: dict[str, Optional[pd.DataFrame]],
    is_fixture: bool = False,
    overlap_diagnostics: Optional[dict] = None,
) -> None:
    """
    Export sensor comparison and overlap diagnostics.

    Parameters
    ----------
    agg_by_sensor        : sensor -> aggregated DataFrame (from aggregate.py)
    is_fixture           : True when using synthetic test data
    overlap_diagnostics  : Optional dict from harmonize.diagnostics_to_dict()
                           If None, a basic comparison is computed inline.

    Schema v1.0.0
    -------------
    Per period within the common overlap, shows both sensor values side by side.
    Limitations are explicitly stated.
    """
    frames = {}
    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        df = agg_by_sensor.get(sensor)
        if df is not None:
            frames[sensor] = df[["period", "year", "month", "detection_count",
                                  "occupied_cell_fraction", "has_data"]].copy()

    # Use provided diagnostics or build a simple inline comparison
    if overlap_diagnostics is not None:
        diag_out = overlap_diagnostics
    else:
        # Fallback: simple period-by-period comparison (no Spearman etc.)
        overlap_periods: list = []
        if len(frames) == 2:
            modis_periods = set(frames[SENSOR_MODIS][frames[SENSOR_MODIS]["has_data"]]["period"])
            viirs_periods = set(frames[SENSOR_VIIRS][frames[SENSOR_VIIRS]["has_data"]]["period"])
            common        = sorted(modis_periods & viirs_periods)

            for period in common:
                m_row = frames[SENSOR_MODIS][frames[SENSOR_MODIS]["period"] == period]
                v_row = frames[SENSOR_VIIRS][frames[SENSOR_VIIRS]["period"] == period]
                m_ocf = _safe_float(m_row["occupied_cell_fraction"].iloc[0]) if len(m_row) else None
                v_ocf = _safe_float(v_row["occupied_cell_fraction"].iloc[0]) if len(v_row) else None
                overlap_periods.append({
                    "period": period,
                    "modis_ocf":  m_ocf,
                    "viirs_ocf":  v_ocf,
                    "ratio_viirs_to_modis": (
                        round(v_ocf / m_ocf, 4)
                        if (m_ocf and v_ocf and m_ocf > 0) else None
                    ),
                })
        diag_out = {
            "overlap_periods": overlap_periods,
            "n_overlap_months": len(overlap_periods),
            "harmonization_supported": False,
            "harmonization_note": "Harmonization not applied; separate sensor series retained.",
            "limitations": [
                "Common gridding reduces duplicate detections but does not equalise sensor sensitivity.",
                "MODIS and VIIRS have different spatial resolutions, overpass times and detection thresholds.",
                "ratio_viirs_to_modis is an observation-level ratio, not a calibration factor.",
                "Apparent seasonal differences may reflect sensor characteristics, not actual fire differences.",
            ],
        }

    data = {
        "contract_version": CONTRACT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "generated_at": _now_utc(),
        "is_fixture": is_fixture,
        "fixture_warning": "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT" if is_fixture else None,
        "region_id": REGION_ID,
        "sensor_metadata": {
            sensor: {
                "label": SENSOR_LABELS.get(sensor, sensor),
                "available": frames.get(sensor) is not None,
            }
            for sensor in (SENSOR_MODIS, SENSOR_VIIRS)
        },
        "overlap_diagnostics": diag_out,
    }
    _write("sensors.json", data)


# ---------------------------------------------------------------------------
# reliability.json
# ---------------------------------------------------------------------------
def export_reliability(
    reliability_df: pd.DataFrame,
    stability_df: pd.DataFrame,
) -> None:
    """
    Export reliability / classification stability results.

    Schema v1.0.0
    """
    config_meta = {
        name: {k: v for k, v in cfg.items()}
        for name, cfg in RELIABILITY_CONFIGS.items()
    }

    per_period: list = []
    if not stability_df.empty:
        for _, row in stability_df.iterrows():
            per_period.append({
                "period":          row["period"],
                "year":            int(row["year"]),
                "month":           int(row["month"]),
                "stability_label": row["stability_label"],
                "n_configs_total": int(row["n_configs_total"]),
                "n_elevated":      int(row["n_elevated"]),
                "n_not_elevated":  int(row["n_not_elevated"]),
                "n_insufficient":  int(row["n_insufficient"]),
                "n_evaluable":     int(row["n_evaluable"]),
                "min_evaluable_required": int(row["min_evaluable_required"]),
                "evaluable_fraction": float(row["evaluable_fraction"]),
                "n_not_run":       int(row.get("n_not_run", 0)),
                "cross_sensor_requirement_met": bool(row.get("cross_sensor_requirement_met", False)),
                "sensors_lacking_evaluable_config": [
                    x for x in str(row.get("sensors_lacking_evaluable_config", "")).split(",") if x
                ],
                "sensor_specific": {
                    sensor: {
                        "n_configs": int(row.get(f"{key}_n_configs", 0)),
                        "n_evaluable": int(row.get(f"{key}_n_evaluable", 0)),
                        "n_elevated": int(row.get(f"{key}_n_elevated", 0)),
                        "n_not_elevated": int(row.get(f"{key}_n_not_elevated", 0)),
                        "label": str(row.get(f"{key}_label", LABEL_INSUFFICIENT_EVIDENCE)),
                    }
                    for sensor, key in ((SENSOR_MODIS, "modis"), (SENSOR_VIIRS, "viirs"))
                },
                "fixture_configs": int(row.get("fixture_configs", 0)),
            })

    data = {
        "contract_version": CONTRACT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "generated_at": _now_utc(),
        "region_id": REGION_ID,
        "stability_labels": {
            LABEL_CONSISTENTLY_ELEVATED:   "All evaluated configurations classify this period as elevated",
            LABEL_NOT_ELEVATED:            "All evaluated configurations classify this period as not elevated",
            LABEL_CLASSIFICATION_SENSITIVE:"Configurations disagree on the classification",
            LABEL_INSUFFICIENT_EVIDENCE:   "Fewer than min_evaluable_configs configurations produced an evaluable result",
            LABEL_INSUFFICIENT_CROSS_SENSOR: (
                "Enough configurations were evaluable, but not every required sensor had an "
                "evaluable configuration; no cross-sensor agreement label is assigned. See "
                "sensor_specific for single-sensor findings."
            ),
        },
        "sensor_specific_labels": {
            "elevated": "All evaluable configurations of this sensor classify the period as elevated",
            "not_elevated": "All evaluable configurations of this sensor classify the period as not elevated",
            "mixed": "This sensor's evaluable configurations disagree",
            "insufficient_evidence": "This sensor has no evaluable configuration for the period",
        },
        "cross_sensor_rule": {
            "min_evaluable_configs": RELIABILITY_MIN_EVALUABLE_CONFIGS,
            "required_sensors": list(RELIABILITY_REQUIRED_SENSORS),
            "min_evaluable_per_sensor": RELIABILITY_MIN_EVALUABLE_PER_SENSOR,
            "evaluable_means": "configuration result is consistently_elevated or not_elevated",
            "never_counted_as_agreement": [
                "insufficient_evidence configuration results",
                "configurations that did not run (n_not_run), e.g. sensor data absent",
            ],
        },
        "configurations": config_meta,
        "config_registry_version": RELIABILITY_CONFIG_REGISTRY_VERSION,
        "config_registry_history": {str(k): v for k, v in RELIABILITY_CONFIG_REGISTRY_HISTORY.items()},
        "per_period": per_period,
        "limitations": [
            "Reliability is classification stability across predefined analytical choices, "
            "not a calibrated probability of truth.",
            "Configurations are fixed before analysis; do not add post-hoc configurations.",
            "Insufficient evidence does not mean no fire activity; it means the data "
            "or baseline do not support a classification.",
            "Insufficient-evidence configurations are never counted as agreement. A period "
            "is labelled consistently_elevated or not_elevated only when at least "
            "min_evaluable_required configurations produced an evaluable result.",
            "Configurations that share a sensor are not independent (3 MODIS and 2 VIIRS "
            "configurations). Cross-sensor agreement labels therefore require at least one "
            "evaluable MODIS and one evaluable VIIRS configuration.",
            "sensor_specific findings describe one sensor only and are not cross-sensor agreement. "
            "A sensor-specific label can rest on a single configuration.",
            "Disagreement between sensors reflects analytical sensitivity to sensor choice; it "
            "does not show which sensor is closer to actual fire occurrence.",
        ],
        "min_evaluable_configs": RELIABILITY_MIN_EVALUABLE_CONFIGS,
        "is_fixture": bool(reliability_df["is_fixture"].any())
        if (not reliability_df.empty and "is_fixture" in reliability_df.columns) else True,
    }
    data["fixture_warning"] = FIXTURE_WARNING if data["is_fixture"] else None
    _write("reliability.json", data)


# ---------------------------------------------------------------------------
# methodology.json
# ---------------------------------------------------------------------------
def export_methodology(is_fixture: bool = False) -> None:
    """
    Export processing assumptions, limitations and provenance metadata.

    Schema v1.0.0
    """
    (
        modis_versions,
        modis_source_types,
        modis_versions_by_type,
    ) = _source_manifest_details(SENSOR_MODIS, is_fixture)
    (
        viirs_versions,
        viirs_source_types,
        viirs_versions_by_type,
    ) = _source_manifest_details(SENSOR_VIIRS, is_fixture)
    data = {
        "contract_version": CONTRACT_VERSION,
        "processing_version": PROCESSING_VERSION,
        "generated_at": _now_utc(),
        "is_fixture": is_fixture,
        "fixture_warning": FIXTURE_WARNING if is_fixture else None,
        "region": {
            "id": REGION_ID,
            "name": REGION_NAME,
            "bbox": list(BBOX),
            "source": "Engineering Blueprint §3.1",
        },
        "data_sources": [
            {
                "sensor": SENSOR_MODIS,
                "product": _modis_product_description(modis_versions),
                "provider": "NASA FIRMS",
                "url": "https://firms.modaps.eosdis.nasa.gov/",
                "temporal_coverage": f"{YEAR_START}–{YEAR_END}",
                "access_method": "NASA FIRMS CSV downloads",
                "product_versions": modis_versions,
                "source_types": modis_source_types,
                "source_versions_by_type": modis_versions_by_type,
            },
            {
                "sensor": SENSOR_VIIRS,
                "product": "VIIRS NOAA-20 (J1) Collection 2 Active Fire",
                "provider": "NASA FIRMS",
                "url": "https://firms.modaps.eosdis.nasa.gov/",
                "temporal_coverage": f"{YEAR_START}–{YEAR_END}",
                "access_method": "NASA FIRMS CSV downloads",
                "product_versions": viirs_versions,
                "source_types": viirs_source_types,
                "source_versions_by_type": viirs_versions_by_type,
            },
        ],
        "processing_steps": [
            "1. Ingest raw NASA FIRMS CSV files; record per-file manifest.",
            "2. Validate schema, coordinates, timestamps and confidence flags.",
            "3. Normalize: cast types, parse UTC datetime, exclude low-confidence and duplicate rows.",
            "4. Spatial filter: clip to South Sumatra bounding box.",
            "5. Grid assignment: floor(coordinate / resolution) × resolution; points on the upper box edges clamp into the last cell.",
            f"6. Monthly aggregation: occupied-cell fraction at {GRID_RESOLUTION_DEG_PRIMARY}° resolution using "
            "Convention B (every cell intersecting the box); Convention A reported as a sensitivity value.",
            "7. Seasonal baseline: per-calendar-month median over baseline window.",
            "8. Anomaly: observed value minus baseline median.",
            f"9. Elevated classification: above the {RELIABILITY_CONFIGS['primary']['elevated_quantile']*100:.0f}th percentile "
            "of the same calendar month across baseline years.",
            "10. Reliability: repeat classification across all predefined configurations; cross-sensor "
            "agreement labels need >= 2 evaluable configurations including >= 1 MODIS and >= 1 VIIRS.",
        ],
        "index_definition": {
            "name": "occupied_cell_fraction",
            "formula": "eligible_cells_with_at_least_one_detection / total_eligible_cells",
            "unit": "fraction of grid cells [0, 1] (dimensionless count ratio)",
            "denominator": "Convention B: every grid cell intersecting the bounding box (288 at 0.25°, 72 at 0.5°)",
            "not_area_weighted": True,
            "interpretation_caveat": AREA_CAVEAT,
            "limitations": [
                "Each eligible cell has weight 1; boundary cells partly outside the box count as whole cells.",
                "Cell area varies with latitude; the index is not converted to km2.",
                "Sensitive to grid resolution; tested at two resolutions.",
                "Does not account for differences in sensor detection sensitivity.",
                "Missing months are represented as null, not zero.",
                "Short 2019–2024 baseline (max 6 observations per calendar month).",
            ],
        },
        "baseline_window": {
            "start": BASELINE_YEAR_START,
            "end":   BASELINE_YEAR_END,
            "note":  "Full available window; declared before analysis.",
        },
        "geographic_support": {
            "primary_convention": "B: every grid cell intersecting the bounding box",
            "sensitivity_convention": "A: grid cells whose lower-left origin lies inside the bounding box",
            "metric_definitions": METRIC_DEFINITIONS,
            "decision": "Convention B approved as primary; Convention A retained as sensitivity comparison (processing version 0.2.0).",
            "note": (
                "Convention B includes every in-bounds detection. Its partial boundary cells extend "
                "outside the box, so the cells cover more area than the box itself. Convention A "
                "covers only cells fully inside the box and leaves a southern strip uncovered. "
                "Areas are square degrees, not km2."
            ),
            "cell_counts": [
                grid_cell_counts(resolution=r, convention=c)
                for r in (GRID_RESOLUTION_DEG_PRIMARY, GRID_RESOLUTION_DEG_SENSITIVITY)
                for c in (GRID_CONVENTION_PRIMARY, GRID_CONVENTION_SENSITIVITY)
            ],
            "by_resolution": [
                grid_geographic_support(resolution=GRID_RESOLUTION_DEG_PRIMARY),
                grid_geographic_support(resolution=GRID_RESOLUTION_DEG_SENSITIVITY),
            ],
        },
        "reliability_min_evaluable_configs": RELIABILITY_MIN_EVALUABLE_CONFIGS,
        "reliability_cross_sensor_rule": {
            "required_sensors": list(RELIABILITY_REQUIRED_SENSORS),
            "min_evaluable_per_sensor": RELIABILITY_MIN_EVALUABLE_PER_SENSOR,
        },
        "reliability_configurations": RELIABILITY_CONFIGS,
        "reliability_config_registry_version": RELIABILITY_CONFIG_REGISTRY_VERSION,
        "scientific_guardrails": [
            "Hotspots are satellite thermal-anomaly detections, not unique fires, "
            "burned area, severity, ignition causes or fire forecasts.",
            "MODIS and VIIRS records are NOT directly interchangeable.",
            "Common gridding does not equalise sensor sensitivity.",
            "Missing observations are not confirmed zero activity.",
            "Reliability labels are stability measures, not calibrated probabilities of truth.",
            "Harmonization effectiveness has not been independently validated.",
            AREA_CAVEAT,
        ],
    }
    for source in data["data_sources"]:
        source_types = source["source_types"]
        source_types_label = " and ".join("NRT" if item == "nrt" else item for item in source_types)
        if source_types:
            source["provenance_note"] = (
                f"Source manifests retain {source_types_label} files separately; "
                f"only records within the {YEAR_START}–{YEAR_END} analysis window are included."
            )
        elif is_fixture:
            source["provenance_note"] = (
                "Source file status and product-version IDs are not supplied for fixture data."
            )
        else:
            source["provenance_note"] = (
                f"Source file status is unavailable; the analysis window is {YEAR_START}–{YEAR_END}."
            )
    _write("methodology.json", data)


# ---------------------------------------------------------------------------
# Convenience: export all
# ---------------------------------------------------------------------------
def export_all(
    agg_by_sensor: dict[str, Optional[pd.DataFrame]],
    anomaly_by_sensor: dict[str, Optional[pd.DataFrame]],
    reliability_df: pd.DataFrame,
    stability_df: pd.DataFrame,
    is_fixture: bool = False,
    overlap_diagnostics: Optional[dict] = None,
    agg_a_by_sensor: Optional[dict[str, Optional[pd.DataFrame]]] = None,
) -> None:
    """Export all five frontend JSON contracts."""
    export_regions(is_fixture=is_fixture)
    export_calendar(agg_by_sensor, anomaly_by_sensor, is_fixture=is_fixture,
                    agg_a_by_sensor=agg_a_by_sensor)
    export_sensors(agg_by_sensor, is_fixture=is_fixture,
                   overlap_diagnostics=overlap_diagnostics)
    export_reliability(reliability_df, stability_df)
    export_methodology(is_fixture=is_fixture)
    logger.info("All JSON contracts exported to %s", FRONTEND_DATA)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _safe_float(val: Any) -> Optional[float]:
    """Convert to float; return None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else round(f, 6)
    except (TypeError, ValueError):
        return None
