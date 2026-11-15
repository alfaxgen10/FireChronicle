#!/usr/bin/env python
"""
Leave-one-year-out (LOO) diagnostic on the real 2019–2024 data.

Usage
-----
    python scripts/run_loo_diagnostic.py --raw-dir <path to data/raw> [--json OUT]

For each configuration, sensor, year and calendar month, the excluded year is
classified against the q-quantile of the remaining five years
(``baseline.compute_loo_classification``) and compared with the in-sample
classification (``baseline.compute_anomalies`` on 2019–2024 only, the released
method). Read-only: raw files are read, nothing in the repository is written,
manifests are not regenerated. The released contracts are not changed.

The build stops if the in-sample primary-configuration labels do not reproduce
the released calendar.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from pipeline import ingest  # noqa: E402
from pipeline.aggregate import aggregate_monthly  # noqa: E402
from pipeline.baseline import compute_anomalies, compute_loo_classification, compute_seasonal_baseline  # noqa: E402
from pipeline.config import (  # noqa: E402
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    LABEL_CONSISTENTLY_ELEVATED,
    RELIABILITY_CONFIGS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.normalize import normalize  # noqa: E402
from pipeline.recent_activity import compare_history  # noqa: E402

SUBDIRS = {SENSOR_MODIS: "modis", SENSOR_VIIRS: "viirs"}


def _clean(raw_dir: Path, sensor: str) -> pd.DataFrame:
    manifest = json.loads((PROJECT_ROOT / f"data/manifests/{sensor}_manifest.json").read_text(encoding="utf-8"))
    sha_by_name = {e["filename"]: e["sha256"] for e in manifest["files"]}
    frames = []
    for source_type in ("archive", "nrt"):
        (path,) = sorted((raw_dir / SUBDIRS[sensor] / source_type).glob("*.csv"))
        if sha_by_name.get(path.name) != ingest._sha256(path):
            raise SystemExit(f"{path.name}: SHA-256 does not match the manifest")
        df = ingest._load_csv(path)
        df["_source_type"], df["_source_file"], df["_sensor"] = source_type, path.name, sensor
        frames.append(df)
    clean, _ = normalize(pd.concat(frames, ignore_index=True), sensor)  # default 2019–2024 window
    return clean


def run(raw_dir: Path) -> dict:
    calendar = json.loads((PROJECT_ROOT / "web/public/data/calendar.json").read_text(encoding="utf-8"))
    cleaned = {s: _clean(raw_dir, s) for s in (SENSOR_MODIS, SENSOR_VIIRS)}
    results = {}
    for name, cfg in RELIABILITY_CONFIGS.items():
        sensor, q = cfg["sensor"], cfg["elevated_quantile"]
        agg = aggregate_monthly(cleaned[sensor], sensor, resolution=cfg["grid_deg"], convention=cfg["grid_convention"])
        standard = compute_anomalies(agg, compute_seasonal_baseline(agg, BASELINE_YEAR_START, BASELINE_YEAR_END), elevated_quantile=q)
        if name in ("primary", "viirs_primary_grid"):
            check = compare_history(agg, calendar, sensor)
            released = {m["period"]: m["is_elevated"] for m in calendar["sensors"][sensor]["months"]}
            label_mismatch = sum(bool(r.is_elevated) != released[r.period] for r in standard.itertuples())
            if not check["passed"] or label_mismatch:
                raise SystemExit(f"{name}: in-sample results do not reproduce calendar.json ({check}, label mismatches {label_mismatch})")
        loo = compute_loo_classification(standard, elevated_quantile=q).merge(
            standard[["period", "is_elevated"]], on="period")
        evaluable = loo[loo["loo_sufficient"]]
        changed = evaluable[evaluable["agrees_with_standard"] == False]  # noqa: E712
        to_elev = changed[changed["loo_label"] == LABEL_CONSISTENTLY_ELEVATED]
        results[name] = {
            "sensor": sensor, "grid_deg": cfg["grid_deg"], "elevated_quantile": q,
            "periods": int(len(loo)), "evaluable": int(len(evaluable)),
            "changed": int(len(changed)), "stable": int(len(evaluable) - len(changed)),
            "changed_not_to_elevated": int(len(to_elev)),
            "changed_elevated_to_not": int(len(changed) - len(to_elev)),
            "in_sample_elevated": int(standard["is_elevated"].sum()),
            "loo_elevated": int(evaluable["loo_is_elevated"].sum()),
            "changed_by_calendar_month": dict(sorted(Counter(int(m) for m in changed["month"]).items())),
            "changed_periods": sorted(changed["period"].tolist()),
        }
    return results


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None, help="Optional path for a JSON copy of the results")
    args = parser.parse_args()
    results = run(args.raw_dir)
    for name, r in results.items():
        print(f"{name:24} {r['sensor']:12} {r['grid_deg']}deg q={r['elevated_quantile']}: "
              f"evaluable {r['evaluable']}/{r['periods']}, stable {r['stable']}, changed {r['changed']} "
              f"(not->elevated {r['changed_not_to_elevated']}, elevated->not {r['changed_elevated_to_not']}); "
              f"elevated in-sample {r['in_sample_elevated']} vs LOO {r['loo_elevated']}; by month {r['changed_by_calendar_month']}")
    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
