"""
FireChronicle — reliability / sensitivity analysis.

Recomputes activity classification across the predefined set of configurations
declared in config.py (RELIABILITY_CONFIGS).  Classification agreement across
configurations produces the stability label shown in the Reliability Lab screen.

Blueprint §3.4:
  "Reliability is the stability of that classification across documented
   sensor/grid/baseline choices; it is not a calibrated probability of truth."

Stability labels (Blueprint §3.4):
  - consistently_elevated    : all supported configurations agree "elevated"
  - classification_sensitive : configurations disagree
  - insufficient_evidence    : coverage or comparison requirements fail
  - not_elevated             : all supported configurations agree "not elevated"

IMPORTANT: This module uses synthetic normalized data when real data are absent,
clearly labelling results as fixtures.  It NEVER presents fixture results as
actual observations.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from pipeline.aggregate import aggregate_monthly
from pipeline.baseline import compute_anomalies, compute_seasonal_baseline
from pipeline.config import (
    GRID_CONVENTION_PRIMARY,
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_CROSS_SENSOR,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    RELIABILITY_CONFIGS,
    RELIABILITY_MIN_EVALUABLE_CONFIGS,
    RELIABILITY_MIN_EVALUABLE_PER_SENSOR,
    RELIABILITY_REQUIRED_SENSORS,
    SENSOR_LABEL_ELEVATED,
    SENSOR_LABEL_INSUFFICIENT,
    SENSOR_LABEL_MIXED,
    SENSOR_LABEL_NOT_ELEVATED,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)

logger = logging.getLogger(__name__)


def run_reliability_experiment(
    normalized_data: dict[str, Optional[pd.DataFrame]],
    configs: dict = RELIABILITY_CONFIGS,
    is_fixture: bool = False,
) -> pd.DataFrame:
    """
    Run all reliability configurations and return a summary DataFrame.

    Parameters
    ----------
    normalized_data : Dict sensor -> clean DataFrame (from normalize.py)
                      Value may be None if sensor data are unavailable.
    configs         : Configuration dict (default: RELIABILITY_CONFIGS from config.py)
    is_fixture      : True when synthetic fixture data are being used.
                      This flag is propagated to every output row so that
                      fixture-derived results can never be mistaken for
                      validated scientific outputs.
    """
    all_results = []

    for config_name, cfg in configs.items():
        sensor     = cfg["sensor"]
        grid_deg   = cfg["grid_deg"]
        bl_start   = cfg["baseline_start"]
        bl_end     = cfg["baseline_end"]
        elev_q     = cfg["elevated_quantile"]

        # Retrieve normalized data for this configuration's sensor
        df_norm = normalized_data.get(sensor)

        if df_norm is None:
            logger.warning(
                "reliability: sensor %s not available for config %s; skipping",
                sensor, config_name,
            )
            continue

        # Aggregate at this configuration's grid resolution
        agg = aggregate_monthly(df_norm, sensor, resolution=grid_deg,
                                convention=cfg.get("grid_convention", GRID_CONVENTION_PRIMARY))

        # Baseline and anomaly
        baseline = compute_seasonal_baseline(agg, bl_start, bl_end)
        result   = compute_anomalies(agg, baseline, elevated_quantile=elev_q)

        result = result.copy()
        result["config_name"]  = config_name
        result["is_fixture"]   = is_fixture

        keep_cols = [
            "period", "year", "month", "config_name", "sensor",
            "resolution_deg", "grid_convention", "occupied_cell_fraction", "is_elevated",
            "anomaly_label", "anomaly_note", "is_fixture",
            "baseline_median", "baseline_n", "sufficient_baseline",
        ]
        keep_cols = [c for c in keep_cols if c in result.columns]
        all_results.append(result[keep_cols])

    if not all_results:
        logger.warning("reliability: no configurations produced results")
        return pd.DataFrame()

    combined = pd.concat(all_results, ignore_index=True)
    return combined


def _sensor_specific_label(n_elevated: int, n_not_elevated: int) -> str:
    """Label for ONE sensor's evaluable configurations. Not a cross-sensor agreement."""
    evaluable = n_elevated + n_not_elevated
    if evaluable == 0:
        return SENSOR_LABEL_INSUFFICIENT
    if n_elevated == evaluable:
        return SENSOR_LABEL_ELEVATED
    if n_not_elevated == evaluable:
        return SENSOR_LABEL_NOT_ELEVATED
    return SENSOR_LABEL_MIXED


def compute_stability_summary(
    reliability_df: pd.DataFrame,
    configs: dict = RELIABILITY_CONFIGS,
) -> pd.DataFrame:
    """
    Summarise per-period stability across all declared configurations.

    Cross-sensor agreement rule (approved scientific decision)
    -----------------------------------------------------------
    A cross-sensor label (consistently_elevated / not_elevated /
    classification_sensitive) is assigned only when:
      1. at least RELIABILITY_MIN_EVALUABLE_CONFIGS configurations are evaluable, and
      2. every sensor in RELIABILITY_REQUIRED_SENSORS has at least
         RELIABILITY_MIN_EVALUABLE_PER_SENSOR evaluable configurations.
    Otherwise:
      - fewer than RELIABILITY_MIN_EVALUABLE_CONFIGS evaluable -> insufficient_evidence
      - enough evaluable but a sensor missing -> insufficient_cross_sensor_evidence
    "Evaluable" means the configuration returned elevated or not_elevated.
    insufficient_evidence results and configurations that could not run
    (sensor data absent) are never counted as agreement.

    Sensor-specific findings are always retained in modis_* / viirs_* columns
    with their own labels (elevated / not_elevated / mixed /
    insufficient_evidence), which describe one sensor only.

    Parameters
    ----------
    reliability_df : Output of run_reliability_experiment()
    configs        : The declared configuration set (used to count configurations
                     that did not run, e.g. because a sensor had no data)
    """
    if reliability_df.empty:
        return pd.DataFrame()

    config_sensor = {name: cfg["sensor"] for name, cfg in configs.items()}
    n_declared = len(configs)

    def _summarise_period(group: pd.DataFrame) -> pd.Series:
        labels = dict(zip(group["config_name"], group["anomaly_label"]))
        n_fixture = int(group["is_fixture"].sum()) if "is_fixture" in group.columns else 0

        # Every declared configuration is accounted for; one that did not run
        # is "not_run" and is not evaluable.
        per_config = {name: labels.get(name, "not_run") for name in config_sensor}
        # Rows for configs not in the declared set (e.g. ad-hoc test configs)
        for name, lab in labels.items():
            if name not in per_config:
                per_config[name] = lab
        sensor_of = dict(config_sensor)
        if "sensor" in group.columns:
            sensor_of.update(dict(zip(group["config_name"], group["sensor"])))

        n_total = len(per_config)
        n_elevated = sum(1 for v in per_config.values() if v == LABEL_CONSISTENTLY_ELEVATED)
        n_not_elevated = sum(1 for v in per_config.values() if v == LABEL_NOT_ELEVATED)
        n_insufficient = sum(1 for v in per_config.values() if v == LABEL_INSUFFICIENT_EVIDENCE)
        n_not_run = sum(1 for v in per_config.values() if v == "not_run")
        evaluable = n_elevated + n_not_elevated

        per_sensor = {}
        for s in RELIABILITY_REQUIRED_SENSORS:
            vals = [v for n, v in per_config.items() if sensor_of.get(n) == s]
            e = sum(1 for v in vals if v == LABEL_CONSISTENTLY_ELEVATED)
            ne = sum(1 for v in vals if v == LABEL_NOT_ELEVATED)
            per_sensor[s] = {
                "n_configs": len(vals),
                "n_evaluable": e + ne,
                "n_elevated": e,
                "n_not_elevated": ne,
                "label": _sensor_specific_label(e, ne),
            }

        sensors_missing = [
            s for s in RELIABILITY_REQUIRED_SENSORS
            if per_sensor[s]["n_evaluable"] < RELIABILITY_MIN_EVALUABLE_PER_SENSOR
        ]
        cross_sensor_ok = not sensors_missing

        if evaluable < RELIABILITY_MIN_EVALUABLE_CONFIGS:
            label = LABEL_INSUFFICIENT_EVIDENCE
        elif not cross_sensor_ok:
            label = LABEL_INSUFFICIENT_CROSS_SENSOR
        elif n_elevated == evaluable:
            label = LABEL_CONSISTENTLY_ELEVATED
        elif n_not_elevated == evaluable:
            label = LABEL_NOT_ELEVATED
        else:
            label = LABEL_CLASSIFICATION_SENSITIVE

        out = {
            "n_configs_total": n_total,
            "n_configs_declared": n_declared,
            "n_elevated": n_elevated,
            "n_not_elevated": n_not_elevated,
            "n_insufficient": n_insufficient,
            "n_not_run": n_not_run,
            "n_evaluable": evaluable,
            "min_evaluable_required": RELIABILITY_MIN_EVALUABLE_CONFIGS,
            "evaluable_fraction": round(evaluable / n_total, 4) if n_total else 0.0,
            "cross_sensor_requirement_met": cross_sensor_ok,
            "sensors_lacking_evaluable_config": ",".join(sensors_missing),
            "fixture_configs": n_fixture,
            "stability_label": label,
        }
        for s, d in per_sensor.items():
            key = s.split("_")[0].lower()   # MODIS_C61 -> modis, VIIRS_J1_C2 -> viirs
            out[f"{key}_n_configs"] = d["n_configs"]
            out[f"{key}_n_evaluable"] = d["n_evaluable"]
            out[f"{key}_n_elevated"] = d["n_elevated"]
            out[f"{key}_n_not_elevated"] = d["n_not_elevated"]
            out[f"{key}_label"] = d["label"]
        return pd.Series(out)

    summary = (
        reliability_df
        .groupby(["period", "year", "month"])
        .apply(_summarise_period, include_groups=False)
        .reset_index()
    )

    logger.info(
        "stability_summary: periods=%d consistently_elevated=%d sensitive=%d "
        "not_elevated=%d insufficient=%d insufficient_cross_sensor=%d",
        len(summary),
        int((summary["stability_label"] == LABEL_CONSISTENTLY_ELEVATED).sum()),
        int((summary["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE).sum()),
        int((summary["stability_label"] == LABEL_NOT_ELEVATED).sum()),
        int((summary["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE).sum()),
        int((summary["stability_label"] == LABEL_INSUFFICIENT_CROSS_SENSOR).sum()),
    )
    return summary
