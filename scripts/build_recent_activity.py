#!/usr/bin/env python
"""
Build web/public/data/recent_activity.json (historical-to-recent activity assessment).

Usage
-----
    python scripts/build_recent_activity.py --raw-dir <path to data/raw>

The raw FIRMS CSVs are read only; nothing is written next to them. Manifests are
NOT regenerated (``ingest_sensor`` is not called). The five existing JSON contracts
are read, never written.

The build stops with an error if:
- a source file's SHA-256 does not match data/manifests/<sensor>_manifest.json,
- a source file fails validation,
- archive and NRT acquisition dates overlap, or leave a gap between them,
- re-aggregating 2019–2024 does not reproduce the released calendar.json.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from pipeline import ingest  # noqa: E402
from pipeline.aggregate import aggregate_monthly  # noqa: E402
from pipeline.config import (  # noqa: E402
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    GRID_CONVENTION_PRIMARY,
    GRID_RESOLUTION_DEG_PRIMARY,
    MODIS_CONFIDENCE_MIN_INT,
    PROCESSING_VERSION,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    VIIRS_CONFIDENCE_KEEP,
)
from pipeline.normalize import normalize  # noqa: E402
from pipeline.recent_activity import (  # noqa: E402
    HOLDOUT_YEAR,
    PRIMARY_QUANTILE,
    RECENT_YEAR,
    classify_recent,
    compare_history,
    load_frozen_reference,
    summarize,
)
from pipeline.validate import validate_raw  # noqa: E402

RECENT_ACTIVITY_VERSION = "1.0.0"
SENSOR_SUBDIRS = {SENSOR_MODIS: "modis", SENSOR_VIIRS: "viirs"}
SENSOR_LABELS = {SENSOR_MODIS: "MODIS (Terra/Aqua)", SENSOR_VIIRS: "VIIRS (NOAA-20)"}

LIMITATIONS = [
    "Descriptive comparison of an activity index with six historical years (2019–2024) for the same calendar month; not a statistical test, forecast or validated prediction.",
    "Thresholds and medians are frozen at the released 2019–2024 values; 2025 and 2026 observations never enter them.",
    "Elevated means the occupied-cell fraction exceeded the frozen 75th-percentile threshold. It does not show that the number of fires, burned area or damage increased.",
    "MODIS and VIIRS are compared with their own references only. Values are not calibrated to each other and must not be pooled or compared as equivalent fire counts.",
    "Archive and NRT (near-real-time) files are processed with the same rules but are different FIRMS products; NRT records are not reprocessed like archive records, so NRT months are less comparable with the archive-based reference.",
    "Missing months (outside the downloaded files) are null and are not zero activity. FIRMS lists detections only; days without detections are not observation coverage.",
    "Primary configuration only (Convention B, 0.25 degree, q = 0.75). The five-configuration reliability labels are not computed for 2025 or 2026.",
    "Study area is the rectangular South Sumatra-region pilot AOI, not verified against provincial boundaries; partial southern boundary cells count as full cells.",
]


def _source_files(raw_dir: Path, sensor: str) -> dict[str, Path]:
    files = {}
    for source_type in ("archive", "nrt"):
        found = sorted((raw_dir / SENSOR_SUBDIRS[sensor] / source_type).glob("*.csv"))
        if len(found) != 1:
            raise SystemExit(f"{sensor}: expected exactly one {source_type} CSV, found {len(found)}")
        files[source_type] = found[0]
    return files


def build(raw_dir: Path, output: Path) -> dict:
    calendar = json.loads((PROJECT_ROOT / "web/public/data/calendar.json").read_text(encoding="utf-8"))
    sources, records_by_sensor, sensors_out, history_checks = [], {}, {}, {}

    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        manifest = json.loads((PROJECT_ROOT / f"data/manifests/{sensor}_manifest.json").read_text(encoding="utf-8"))
        by_name = {e["filename"]: e for e in manifest["files"]}
        frames, coverage, dates = [], {}, {}
        for source_type, path in _source_files(raw_dir, sensor).items():
            sha = ingest._sha256(path)
            entry = by_name.get(path.name)
            if entry is None or entry["sha256"] != sha:
                raise SystemExit(f"{path.name}: SHA-256 does not match {sensor} manifest")
            df = ingest._load_csv(path)
            result = validate_raw(df, sensor, entry["path"], source_type=source_type)
            if not result.is_valid:
                raise SystemExit(f"{path.name}: validation failed: {result.errors}")
            acq = pd.to_datetime(df["acq_date"], errors="coerce").dropna()
            dates[source_type] = set(acq.dt.date)
            coverage[source_type] = (acq.min().date(), acq.max().date())
            df["_source_type"] = source_type
            df["_source_file"] = path.name
            df["_sensor"] = sensor
            frames.append(df)
            sources.append({
                "sensor": sensor, "source_type": source_type, "filename": path.name,
                "path": entry["path"], "sha256": sha, "rows": int(len(df)),
                "date_min": coverage[source_type][0].isoformat(),
                "date_max": coverage[source_type][1].isoformat(),
                "product_versions": sorted(df["version"].dropna().unique().tolist()),
            })
        overlap = dates["archive"] & dates["nrt"]
        if overlap:
            raise SystemExit(f"{sensor}: archive and NRT share {len(overlap)} acquisition dates")
        if (pd.Timestamp(coverage["archive"][1]) + pd.Timedelta(days=1)).date() != coverage["nrt"][0]:
            raise SystemExit(f"{sensor}: archive and NRT date ranges are not contiguous: {coverage}")

        raw = pd.concat(frames, ignore_index=True)
        clean, stats = normalize(raw, sensor, year_range=range(BASELINE_YEAR_START, RECENT_YEAR + 1))
        agg = aggregate_monthly(clean, sensor, year_start=BASELINE_YEAR_START, year_end=RECENT_YEAR)

        check = compare_history(agg, calendar, sensor)
        if not check["passed"]:
            raise SystemExit(f"{sensor}: 2019–2024 re-aggregation does not reproduce calendar.json: {check}")
        history_checks[sensor] = check

        reference = load_frozen_reference(calendar, sensor)
        recent = agg[agg["year"] >= HOLDOUT_YEAR].copy()
        records = classify_recent(sensor, recent, reference, coverage)
        records_by_sensor[sensor] = records
        sensors_out[sensor] = {
            "label": SENSOR_LABELS[sensor],
            "source_coverage": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in coverage.items()},
            "normalization": {
                "rows_in": stats.rows_in, "excluded_low_confidence": stats.excluded_low_confidence,
                "excluded_duplicates": stats.excluded_duplicates, "excluded_outside_years": stats.excluded_outside_years,
                "rows_out": stats.rows_out,
            },
            "reference": [reference[m] for m in range(1, 13)],
            "records": records,
        }

    payload = {
        "recent_activity_version": RECENT_ACTIVITY_VERSION,
        "based_on_contract_version": calendar["contract_version"],
        "processing_version": PROCESSING_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_fixture": False,
        "region_id": calendar["region_id"],
        "configuration": {
            "grid_convention": GRID_CONVENTION_PRIMARY,
            "grid_resolution_deg": GRID_RESOLUTION_DEG_PRIMARY,
            "elevated_quantile": PRIMARY_QUANTILE,
            "elevated_rule": "occupied_cell_fraction > frozen elevated_threshold",
            "metric": "occupied_cell_fraction",
            "quality_filters": {
                SENSOR_MODIS: f"confidence >= {MODIS_CONFIDENCE_MIN_INT} (integer 0-100)",
                SENSOR_VIIRS: f"confidence in {sorted(VIIRS_CONFIDENCE_KEEP)}",
            },
            "historical_rank_definition": "rank 1 to 7 among the six 2019-2024 values for the same calendar month plus this month; 1 = no historical value is higher, 7 = all six are higher; ties (equal values, compared at 6 decimals) share the higher rank.",
        },
        "periods": {
            "reference": {"start": BASELINE_YEAR_START, "end": BASELINE_YEAR_END, "source": "calendar.json (frozen)"},
            "holdout": {"year": HOLDOUT_YEAR},
            "recent": {"year": RECENT_YEAR},
        },
        "sources": sources,
        "historical_reproduction_check": history_checks,
        "sensors": sensors_out,
        "summary": summarize(records_by_sensor),
        "limitations": LIMITATIONS,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return payload


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, required=True, help="Directory containing modis/ and viirs/ raw FIRMS folders")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "web/public/data/recent_activity.json")
    args = parser.parse_args()
    payload = build(args.raw_dir, args.output)
    for sensor, years in payload["summary"]["by_sensor"].items():
        for year, s in years.items():
            print(f"{sensor} {year}: elevated {s['n_elevated']} months {s['elevated_months']}; missing {s['months_missing']}")
    print("both sensors elevated:", payload["summary"]["both_sensors_elevated"])


if __name__ == "__main__":
    main()
