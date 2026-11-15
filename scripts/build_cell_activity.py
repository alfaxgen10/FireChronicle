#!/usr/bin/env python
"""
Build web/public/data/cell_activity.json: quality-filtered detection counts per
0.25° grid cell, per month and per sensor, for the map on the Overview page.

Usage
-----
    python scripts/build_cell_activity.py --raw-dir <path to data/raw>

Uses the same reading, validation, normalization and grid assignment as the
released pipeline. Raw FIRMS CSVs are read only. The build stops with an error if
- a source file's SHA-256 does not match data/manifests/<sensor>_manifest.json,
- a source file fails validation,
- per-cell totals do not reproduce detection_count and occupied_cells for every
  month in calendar.json (2019-2024) and recent_activity.json (2025-2026).
No point coordinates are exported: only cell counts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from pipeline import ingest  # noqa: E402
from pipeline.aggregate import _assign_grid_cells, aggregate_monthly, build_grid  # noqa: E402
from pipeline.config import (  # noqa: E402
    BASELINE_YEAR_START,
    BBOX,
    GRID_CONVENTION_PRIMARY,
    GRID_RESOLUTION_DEG_PRIMARY,
    PROCESSING_VERSION,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.normalize import normalize  # noqa: E402
from pipeline.recent_activity import RECENT_YEAR  # noqa: E402
from pipeline.validate import validate_raw  # noqa: E402

CELL_ACTIVITY_VERSION = "1.0.0"
SENSOR_SUBDIRS = {SENSOR_MODIS: "modis", SENSOR_VIIRS: "viirs"}


def _load_sensor(raw_dir: Path, sensor: str):
    manifest = json.loads((PROJECT_ROOT / f"data/manifests/{sensor}_manifest.json").read_text(encoding="utf-8"))
    by_name = {e["filename"]: e for e in manifest["files"]}
    frames, sources, coverage = [], [], {}
    for source_type in ("archive", "nrt"):
        found = sorted((raw_dir / SENSOR_SUBDIRS[sensor] / source_type).glob("*.csv"))
        if len(found) != 1:
            raise SystemExit(f"{sensor}: expected exactly one {source_type} CSV, found {len(found)}")
        path = found[0]
        sha = ingest._sha256(path)
        entry = by_name.get(path.name)
        if entry is None or entry["sha256"] != sha:
            raise SystemExit(f"{path.name}: SHA-256 does not match {sensor} manifest")
        df = ingest._load_csv(path)
        result = validate_raw(df, sensor, entry["path"], source_type=source_type)
        if not result.is_valid:
            raise SystemExit(f"{path.name}: validation failed: {result.errors}")
        acq = pd.to_datetime(df["acq_date"], errors="coerce").dropna()
        coverage[source_type] = (acq.min().date().isoformat(), acq.max().date().isoformat())
        df["_source_type"] = source_type
        df["_source_file"] = path.name
        df["_sensor"] = sensor
        frames.append(df)
        sources.append({"sensor": sensor, "source_type": source_type, "filename": path.name, "sha256": sha,
                        "date_min": coverage[source_type][0], "date_max": coverage[source_type][1]})
    raw = pd.concat(frames, ignore_index=True)
    clean, _ = normalize(raw, sensor, year_range=range(BASELINE_YEAR_START, RECENT_YEAR + 1))
    return clean, sources, coverage


def build(raw_dir: Path, output: Path) -> dict:
    calendar = json.loads((PROJECT_ROOT / "web/public/data/calendar.json").read_text(encoding="utf-8"))
    recent = json.loads((PROJECT_ROOT / "web/public/data/recent_activity.json").read_text(encoding="utf-8"))
    resolution = GRID_RESOLUTION_DEG_PRIMARY
    grid = build_grid(BBOX, resolution, GRID_CONVENTION_PRIMARY).sort_values(["cell_lat", "cell_lon"], ascending=[False, True]).reset_index(drop=True)
    cell_index = {(round(lon, 8), round(lat, 8)): i for i, (lon, lat) in enumerate(zip(grid["cell_lon"], grid["cell_lat"]))}

    sensors_out, all_sources, checks = {}, [], {}
    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        clean, sources, coverage = _load_sensor(raw_dir, sensor)
        all_sources += sources

        # Same grid assignment and bbox filter as aggregate_monthly.
        df = _assign_grid_cells(clean, resolution, bbox=BBOX)
        lon_min, lat_min, lon_max, lat_max = BBOX
        df = df[(df["longitude"] >= lon_min) & (df["longitude"] <= lon_max)
                & (df["latitude"] >= lat_min) & (df["latitude"] <= lat_max)]
        counts = df.groupby(["year", "month", "cell_lon", "cell_lat"]).size().reset_index(name="n")

        periods: dict[str, list[list[int]]] = {}
        for row in counts.itertuples(index=False):
            key = (round(row.cell_lon, 8), round(row.cell_lat, 8))
            if key not in cell_index:
                raise SystemExit(f"{sensor}: detection assigned to a cell outside the grid: {key}")
            periods.setdefault(f"{int(row.year):04d}-{int(row.month):02d}", []).append([cell_index[key], int(row.n)])
        for value in periods.values():
            value.sort()

        # Reproduction checks against the released exports.
        agg = aggregate_monthly(clean, sensor, year_start=BASELINE_YEAR_START, year_end=RECENT_YEAR)
        expected = {m["period"]: (m["detection_count"], m["occupied_cells"]) for m in calendar["sensors"][sensor]["months"]}
        for r in recent["sensors"][sensor]["records"]:
            if r["has_data"]:
                row = agg[agg["period"] == r["period"]].iloc[0]
                expected[r["period"]] = (int(row["detection_count"]), int(row["occupied_cells"]))
                # recent_activity.json stores fractions rounded to 6 decimals.
                if round(float(row["occupied_cell_fraction"]), 6) != r["occupied_cell_fraction"]:
                    raise SystemExit(f"{sensor} {r['period']}: fraction differs from recent_activity.json")
        mismatches = []
        for period, (n_det, n_occ) in expected.items():
            cells = periods.get(period, [])
            got = (sum(c[1] for c in cells), len(cells))
            if got != (n_det, n_occ):
                mismatches.append((period, got, (n_det, n_occ)))
        if mismatches:
            raise SystemExit(f"{sensor}: per-cell totals do not reproduce the released exports: {mismatches[:5]}")
        checks[sensor] = {"periods_checked": len(expected), "passed": True}
        sensors_out[sensor] = {"source_coverage": coverage, "periods": dict(sorted(periods.items()))}

    payload = {
        "cell_activity_version": CELL_ACTIVITY_VERSION,
        "processing_version": PROCESSING_VERSION,
        "based_on_contract_version": calendar["contract_version"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_fixture": False,
        "region_id": calendar["region_id"],
        "grid": {
            "convention": GRID_CONVENTION_PRIMARY,
            "resolution_deg": resolution,
            "bbox": list(BBOX),
            "cells": [[float(lon), float(lat)] for lon, lat in zip(grid["cell_lon"], grid["cell_lat"])],
            "cell_definition": "cells[i] = [lon, lat] of the south-west corner; each cell spans resolution_deg east and north",
        },
        "metric": "quality-filtered active-fire detection count per cell and month (not fires, burned area or severity)",
        "reproduction_check": checks,
        "sources": all_sources,
        "sensors": sensors_out,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, separators=(",", ":"), ensure_ascii=False)
        fh.write("\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "web/public/data/cell_activity.json")
    args = parser.parse_args()
    payload = build(args.raw_dir, args.output)
    for sensor, block in payload["sensors"].items():
        total = sum(n for cells in block["periods"].values() for _, n in cells)
        print(f"{sensor}: {len(block['periods'])} months, {total} detections, check {payload['reproduction_check'][sensor]}")


if __name__ == "__main__":
    main()
