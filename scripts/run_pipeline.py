#!/usr/bin/env python
"""
FireChronicle — full pipeline runner.

Usage
-----
  python scripts/run_pipeline.py [--fixture]

Flags
-----
  --fixture   Use synthetic fixture data from data/fixtures/ instead of
              requiring real NASA FIRMS files.  Results will be labelled
              as fixtures and must NOT be presented as scientific findings.

Without --fixture the script expects real NASA FIRMS CSV files in:
  data/raw/modis/**/*.csv   — MODIS Active Fire; product versions are recorded in the source manifest
  data/raw/viirs/**/*.csv   — VIIRS NOAA-20 Collection 2

Recognized archive and NRT files retain their source status in manifests and
normalized rows. Ingestion stops for a sensor if archive and NRT dates overlap.

Output
------
  web/public/data/regions.json
  web/public/data/calendar.json
  web/public/data/sensors.json
  web/public/data/reliability.json
  web/public/data/methodology.json
  data/manifests/<sensor>_manifest.json

Scientific note
---------------
Outputs derived from real NASA data include provenance information
traceable to the source files.  Missing months are labelled null,
not zero.  Reliability labels indicate classification stability across
predefined configurations, not calibrated probabilities of truth.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on the import path when called directly
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from pipeline.config import (
    DATA_FIXTURES,
    GRID_CONVENTION_SENSITIVITY,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.ingest import ingest_all
from pipeline.normalize import normalize_all
from pipeline.aggregate import aggregate_all, aggregate_monthly
from pipeline.baseline import compute_seasonal_baseline, compute_anomalies
from pipeline.harmonize import compute_overlap_diagnostics, diagnostics_to_dict
from pipeline.reliability import run_reliability_experiment, compute_stability_summary
from pipeline.export import export_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_pipeline")


def _load_fixture(name: str, sensor: str) -> pd.DataFrame:
    path = DATA_FIXTURES / name
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.lower()
    df["_source_file"] = name
    df["_sensor"]      = sensor
    return df


def run(use_fixtures: bool = False) -> None:
    logger.info("=== FireChronicle pipeline start (fixture=%s) ===", use_fixtures)

    # ------------------------------------------------------------------
    # Stage 1: Ingest
    # ------------------------------------------------------------------
    if use_fixtures:
        logger.info("Loading synthetic fixture data — results are NOT scientific outputs")
        raw_data = {
            SENSOR_MODIS: _load_fixture("modis_sample.csv", SENSOR_MODIS),
            SENSOR_VIIRS: _load_fixture("viirs_sample.csv", SENSOR_VIIRS),
        }
    else:
        logger.info("Loading real NASA FIRMS CSV files from data/raw/")
        raw_data = ingest_all()

    # ------------------------------------------------------------------
    # Stage 2: Normalize
    # ------------------------------------------------------------------
    normalized = normalize_all(raw_data)

    # Unpack for downstream
    norm_dfs: dict[str, pd.DataFrame | None] = {}
    for sensor, item in normalized.items():
        if item is None:
            norm_dfs[sensor] = None
            logger.warning("No normalized data for sensor %s", sensor)
        else:
            df_norm, stats = item
            norm_dfs[sensor] = df_norm
            logger.info(stats.report())

    # ------------------------------------------------------------------
    # Stage 3: Aggregate (sensor-specific monthly series)
    # ------------------------------------------------------------------
    agg_by_sensor = aggregate_all(normalized)

    for sensor, agg in agg_by_sensor.items():
        n_data = int(agg["has_data"].sum())
        logger.info("Aggregated %s: %d months with detections", sensor, n_data)

    # ------------------------------------------------------------------
    # Stage 4: Baseline and anomaly
    # ------------------------------------------------------------------
    anomaly_by_sensor: dict[str, pd.DataFrame | None] = {}
    for sensor, agg in agg_by_sensor.items():
        baseline = compute_seasonal_baseline(agg)
        anomaly  = compute_anomalies(agg, baseline)
        anomaly_by_sensor[sensor] = anomaly

    # ------------------------------------------------------------------
    # Stage 4a: Overlap diagnostics (MODIS vs VIIRS)
    # ------------------------------------------------------------------
    overlap_diag = None
    if (agg_by_sensor.get(SENSOR_MODIS) is not None and
            agg_by_sensor.get(SENSOR_VIIRS) is not None):
        from pipeline.config import SENSOR_MODIS as _SM, SENSOR_VIIRS as _SV
        diag = compute_overlap_diagnostics(
            agg_by_sensor[_SM], agg_by_sensor[_SV]
        )
        overlap_diag = diagnostics_to_dict(diag)
        logger.info(
            "Overlap diagnostics: n_overlap=%d spearman_rho=%s harmonization=%s",
            diag.n_overlap_months,
            f"{diag.spearman_rho:.3f}" if diag.spearman_rho is not None else "N/A",
            diag.harmonization_supported,
        )

    # ------------------------------------------------------------------
    # Stage 5: Reliability sensitivity experiment
    # ------------------------------------------------------------------
    reliability_df = run_reliability_experiment(norm_dfs, is_fixture=use_fixtures)
    stability_df   = compute_stability_summary(reliability_df)

    if not stability_df.empty:
        counts = stability_df["stability_label"].value_counts().to_dict()
        logger.info("Stability summary: %s", counts)

    # ------------------------------------------------------------------
    # Stage 6: Export JSON contracts
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Stage 5a: Convention A sensitivity aggregation (primary is Convention B)
    # ------------------------------------------------------------------
    agg_a_by_sensor = {
        sensor: aggregate_monthly(df_norm, sensor, convention=GRID_CONVENTION_SENSITIVITY)
        for sensor, df_norm in norm_dfs.items()
    }

    export_all(agg_by_sensor, anomaly_by_sensor, reliability_df, stability_df,
               is_fixture=use_fixtures, overlap_diagnostics=overlap_diag,
               agg_a_by_sensor=agg_a_by_sensor)
    logger.info("=== FireChronicle pipeline complete ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FireChronicle pipeline runner")
    parser.add_argument(
        "--fixture",
        action="store_true",
        help="Use synthetic fixture data (for testing without real NASA files)",
    )
    args = parser.parse_args()
    run(use_fixtures=args.fixture)
