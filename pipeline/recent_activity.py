"""
FireChronicle — historical-to-recent activity assessment (primary configuration only).

Compares 2025 (forward holdout) and 2026 (recent activity) monthly occupied-cell
fractions with the FROZEN 2019–2024 reference published in calendar.json.

Rules
-----
- The per-calendar-month baseline median and elevated threshold are read from the
  released calendar.json. They are never recomputed from 2025 or 2026 values.
  ``baseline.compute_anomalies`` is deliberately not used: its threshold quantile is
  taken over every row it receives, so passing recent years would leak them into
  the threshold.
- MODIS and VIIRS are processed and reported separately; nothing is pooled.
- A month without data has ``has_data = False`` and null metrics, never zero.
- "Elevated" means the month's occupied-cell fraction is strictly greater than the
  frozen threshold (the same ">" rule as the historical analysis). It describes the
  activity index relative to six historical years only. It does not show that
  actual fires, burned area or damage increased.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from pipeline.config import (
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    GRID_CONVENTION_PRIMARY,
    GRID_RESOLUTION_DEG_PRIMARY,
)

PRIMARY_QUANTILE = 0.75
HOLDOUT_YEAR = 2025
RECENT_YEAR = 2026
RECENT_YEARS = (HOLDOUT_YEAR, RECENT_YEAR)
REFERENCE_YEARS = tuple(range(BASELINE_YEAR_START, BASELINE_YEAR_END + 1))

# The released JSON rounds metrics to 6 decimals; comparisons use that precision.
JSON_DECIMALS = 6
JSON_TOLERANCE = 1e-6


def _num(value) -> Optional[float]:
    if value is None:
        return None
    value = float(value)
    return None if math.isnan(value) else value


# ---------------------------------------------------------------------------
# Frozen reference
# ---------------------------------------------------------------------------

def load_frozen_reference(calendar: dict, sensor: str) -> dict[int, dict]:
    """Return the frozen 2019–2024 reference per calendar month for one sensor.

    Raises ValueError if the calendar is not the primary configuration, does not
    cover exactly the reference years, or if its stored median/threshold cannot be
    reproduced from its own six monthly values.
    """
    if calendar.get("is_fixture"):
        raise ValueError("calendar.json is a fixture export; refusing to build a reference from it")
    if calendar.get("primary_grid_convention") != GRID_CONVENTION_PRIMARY:
        raise ValueError("calendar.json primary grid convention is not the primary configuration")
    if float(calendar.get("grid_resolution_deg", -1)) != GRID_RESOLUTION_DEG_PRIMARY:
        raise ValueError("calendar.json grid resolution is not the primary 0.25 degree grid")
    window = calendar.get("baseline_window", {})
    if (window.get("start"), window.get("end")) != (BASELINE_YEAR_START, BASELINE_YEAR_END):
        raise ValueError(f"calendar.json baseline window {window} is not {BASELINE_YEAR_START}–{BASELINE_YEAR_END}")
    try:
        months = calendar["sensors"][sensor]["months"]
    except KeyError as exc:
        raise ValueError(f"calendar.json has no months for sensor {sensor!r}") from exc

    years = sorted({m["year"] for m in months})
    if tuple(years) != REFERENCE_YEARS:
        raise ValueError(f"{sensor}: calendar years {years} are not the reference years {list(REFERENCE_YEARS)}")

    reference: dict[int, dict] = {}
    for cal_month in range(1, 13):
        rows = sorted((m for m in months if m["month"] == cal_month), key=lambda m: m["year"])
        if [m["year"] for m in rows] != list(REFERENCE_YEARS):
            raise ValueError(f"{sensor}: calendar month {cal_month} does not have one record per reference year")
        if any(m.get("grid_convention") != GRID_CONVENTION_PRIMARY for m in rows):
            raise ValueError(f"{sensor}: calendar month {cal_month} contains non-primary grid records")
        medians = {_num(m.get("baseline_median")) for m in rows}
        thresholds = {_num(m.get("elevated_threshold")) for m in rows}
        if len(medians) != 1 or len(thresholds) != 1:
            raise ValueError(f"{sensor}: calendar month {cal_month} has inconsistent median/threshold across years")
        median, threshold = medians.pop(), thresholds.pop()
        values = {m["year"]: _num(m["occupied_cell_fraction"]) for m in rows if m.get("has_data")}
        present = [v for v in values.values() if v is not None]
        if threshold is not None:
            if len(present) < 3:
                raise ValueError(f"{sensor}: month {cal_month} has a threshold but fewer than 3 reference values")
            if abs(float(np.quantile(present, PRIMARY_QUANTILE)) - threshold) > JSON_TOLERANCE:
                raise ValueError(f"{sensor}: month {cal_month} threshold is not the q={PRIMARY_QUANTILE} of its reference values")
            if median is None or abs(float(np.median(present)) - median) > JSON_TOLERANCE:
                raise ValueError(f"{sensor}: month {cal_month} median is not the median of its reference values")
        reference[cal_month] = {
            "month": cal_month,
            "baseline_median": median,
            "elevated_threshold": threshold,
            "historical_values": {str(y): values.get(y) for y in REFERENCE_YEARS},
        }
    return reference


# ---------------------------------------------------------------------------
# Source coverage
# ---------------------------------------------------------------------------

def month_source_type(year: int, month: int, coverage: dict[str, tuple[date, date]]) -> Optional[str]:
    """Which source files cover a month: 'archive', 'nrt', 'archive+nrt' or None."""
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    covering = sorted(
        source for source, (first, last) in coverage.items() if first < end and last >= start
    )
    return "+".join(covering) if covering else None


def month_fully_covered(year: int, month: int, coverage: dict[str, tuple[date, date]]) -> bool:
    """True when the union of source date ranges reaches from the 1st to the last day of the month."""
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    first = min((f for f, _ in coverage.values()), default=None)
    last = max((l for _, l in coverage.values()), default=None)
    if first is None:
        return False
    return first <= start and (pd.Timestamp(last) + pd.Timedelta(days=1)).date() >= end


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_recent(
    sensor: str,
    recent_agg: pd.DataFrame,
    reference: dict[int, dict],
    coverage: dict[str, tuple[date, date]],
    years: Iterable[int] = RECENT_YEARS,
) -> list[dict]:
    """Classify each recent month of ONE sensor against the frozen reference.

    ``recent_agg`` is aggregate_monthly output for this sensor. It must not contain
    reference years, so the reference cannot be influenced by it.
    """
    if not recent_agg.empty:
        if set(recent_agg["sensor"].unique()) != {sensor}:
            raise ValueError("recent aggregate must contain exactly one sensor")
        if recent_agg["year"].isin(REFERENCE_YEARS).any():
            raise ValueError("recent aggregate contains reference years; refusing to mix them")
        if (recent_agg["grid_convention"] != GRID_CONVENTION_PRIMARY).any():
            raise ValueError("recent aggregate is not on the primary grid convention")
    rows = {(int(r.year), int(r.month)): r for r in recent_agg.itertuples()}

    records = []
    for year in years:
        if year in REFERENCE_YEARS:
            raise ValueError(f"{year} is a reference year, not a recent year")
        for month in range(1, 13):
            ref = reference[month]
            source = month_source_type(year, month, coverage)
            covered = source is not None and month_fully_covered(year, month, coverage)
            row = rows.get((year, month))
            has_data = bool(covered and row is not None and row.has_data)
            ocf = _num(row.occupied_cell_fraction) if has_data else None
            threshold = ref["elevated_threshold"]
            hist = [v for v in ref["historical_values"].values() if v is not None]

            if source is None:
                note = "outside_downloaded_source_coverage"
            elif not covered:
                note = "partial_month_source_coverage"
            elif not has_data:
                note = "no_detections_after_quality_filtering"
            else:
                note = None

            # Compare at the released JSON precision. The historical values and the
            # threshold come from calendar.json, rounded to 6 decimals; comparing an
            # unrounded recent value with them would turn exact ties (the same number
            # of occupied cells) into arbitrary strict inequalities.
            ocf_cmp = None if ocf is None else round(ocf, JSON_DECIMALS)
            elevated = None if (ocf_cmp is None or threshold is None) else bool(ocf_cmp > threshold)
            n_greater = None if ocf_cmp is None else sum(1 for v in hist if v > ocf_cmp)
            n_tied = None if ocf_cmp is None else sum(1 for v in hist if v == ocf_cmp)
            # Competition ranking among the six historical values plus this month:
            # 1 = no historical value is higher; ties share the higher rank.
            rank = None if n_greater is None else 1 + n_greater
            records.append({
                "sensor": sensor,
                "period": f"{year}-{month:02d}",
                "year": year,
                "month": month,
                "period_role": "holdout" if year == HOLDOUT_YEAR else "recent",
                "source_type": source,
                "has_data": has_data,
                "coverage_note": note,
                "occupied_cell_fraction": None if ocf is None else round(ocf, 6),
                "baseline_median": ref["baseline_median"],
                "elevated_threshold": threshold,
                "anomaly": None if (ocf is None or ref["baseline_median"] is None) else round(ocf - ref["baseline_median"], 6),
                "elevated": elevated,
                "historical_rank": rank,
                "n_historical_values": len(hist),
                "n_historical_values_below": None if ocf_cmp is None else sum(1 for v in hist if v < ocf_cmp),
                "n_historical_values_tied": n_tied,
            })
    return records


def summarize(records_by_sensor: dict[str, list[dict]]) -> dict:
    """Elevated-month lists per sensor and year, and their intersection, derived from the records."""
    summary: dict = {"by_sensor": {}, "both_sensors_elevated": {}}
    for sensor, records in records_by_sensor.items():
        summary["by_sensor"][sensor] = {}
        for year in sorted({r["year"] for r in records}):
            yr = [r for r in records if r["year"] == year]
            summary["by_sensor"][sensor][str(year)] = {
                "months_with_data": sum(r["has_data"] for r in yr),
                "months_missing": [r["month"] for r in yr if not r["has_data"]],
                "n_elevated": sum(r["elevated"] is True for r in yr),
                "elevated_months": [r["month"] for r in yr if r["elevated"] is True],
            }
    sensors = list(records_by_sensor)
    years = sorted({y for s in sensors for y in summary["by_sensor"][s]})
    for year in years:
        sets = [set(summary["by_sensor"][s].get(year, {}).get("elevated_months", [])) for s in sensors]
        summary["both_sensors_elevated"][year] = sorted(set.intersection(*sets)) if sets else []
    return summary


def compare_history(agg: pd.DataFrame, calendar: dict, sensor: str) -> dict:
    """Check that re-aggregated 2019–2024 values equal the released calendar."""
    released = {m["period"]: m for m in calendar["sensors"][sensor]["months"]}
    hist = agg[agg["year"].isin(REFERENCE_YEARS)]
    missing = sorted(set(released) - set(hist["period"]))
    max_diff = 0.0
    count_mismatch = cells_mismatch = flag_mismatch = 0
    for r in hist.itertuples():
        m = released.get(r.period)
        if m is None:
            continue
        a, b = _num(r.occupied_cell_fraction), _num(m["occupied_cell_fraction"])
        if (a is None) != (b is None):
            flag_mismatch += 1
        elif a is not None:
            max_diff = max(max_diff, abs(a - b))
        count_mismatch += int(r.detection_count) != int(m["detection_count"])
        cells_mismatch += int(r.occupied_cells) != int(m["occupied_cells"])
        flag_mismatch += bool(r.has_data) != bool(m["has_data"])
    passed = (not missing and count_mismatch == 0 and cells_mismatch == 0
              and flag_mismatch == 0 and max_diff <= JSON_TOLERANCE)
    return {
        "months_compared": int(len(hist)),
        "missing_periods": missing,
        "max_abs_occupied_cell_fraction_diff": round(max_diff, 9),
        "detection_count_mismatches": count_mismatch,
        "occupied_cells_mismatches": cells_mismatch,
        "has_data_mismatches": flag_mismatch,
        "passed": passed,
    }
