"""Tests for the historical-to-recent activity assessment (pipeline/recent_activity.py)."""

import copy
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.baseline import compute_anomalies, compute_seasonal_baseline
from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS
from pipeline.normalize import normalize
from pipeline.recent_activity import (
    REFERENCE_YEARS,
    classify_recent,
    compare_history,
    load_frozen_reference,
    month_source_type,
    summarize,
)

ROOT = Path(__file__).parent.parent
DATA = ROOT / "web" / "public" / "data"
FULL_COVERAGE = {"archive": (date(2025, 1, 1), date(2026, 7, 31)), "nrt": (date(2026, 8, 1), date(2026, 10, 31))}


# --- synthetic helpers ---------------------------------------------------------

def _calendar(values_by_sensor):
    """calendar.json-shaped dict built with the same rules as the historical analysis."""
    sensors = {}
    for sensor, values in values_by_sensor.items():
        months = []
        for m in range(1, 13):
            vals = [values[(y, m)] for y in REFERENCE_YEARS]
            for y in REFERENCE_YEARS:
                months.append({
                    "period": f"{y}-{m:02d}", "year": y, "month": m, "has_data": True,
                    "occupied_cell_fraction": values[(y, m)], "detection_count": 10, "occupied_cells": 5,
                    "baseline_median": float(np.median(vals)),
                    "elevated_threshold": float(np.quantile(vals, 0.75)),
                    "grid_convention": "B",
                })
        sensors[sensor] = {"months": months}
    return {"is_fixture": False, "primary_grid_convention": "B", "grid_resolution_deg": 0.25,
            "baseline_window": {"start": 2019, "end": 2024}, "sensors": sensors}


def _values(scale=1.0):
    # Distinct values per calendar month: year index 0..5 -> 0.10..0.35 (scaled by month).
    return {(y, m): round(scale * (0.10 + 0.05 * i) * (1 + m / 100), 6)
            for i, y in enumerate(REFERENCE_YEARS) for m in range(1, 13)}


def _recent_agg(sensor, ocf_by_period, missing=()):
    rows = []
    for y in (2025, 2026):
        for m in range(1, 13):
            p = f"{y}-{m:02d}"
            has = p not in missing
            rows.append({"period": p, "year": y, "month": m, "sensor": sensor, "grid_convention": "B",
                         "has_data": has, "occupied_cell_fraction": ocf_by_period.get(p, 0.2) if has else np.nan})
    return pd.DataFrame(rows)


# --- frozen thresholds ---------------------------------------------------------

def test_frozen_reference_reads_calendar_values_exactly():
    cal = _calendar({SENSOR_MODIS: _values()})
    ref = load_frozen_reference(cal, SENSOR_MODIS)
    for m in range(1, 13):
        stored = next(x for x in cal["sensors"][SENSOR_MODIS]["months"] if x["month"] == m)
        assert ref[m]["elevated_threshold"] == stored["elevated_threshold"]
        assert ref[m]["baseline_median"] == stored["baseline_median"]
        assert list(ref[m]["historical_values"]) == [str(y) for y in REFERENCE_YEARS]


def test_recent_observations_do_not_change_thresholds():
    cal = _calendar({SENSOR_MODIS: _values()})
    ref = load_frozen_reference(cal, SENSOR_MODIS)
    frozen = copy.deepcopy(ref)
    extreme = {f"{y}-{m:02d}": 0.99 for y in (2025, 2026) for m in range(1, 13)}
    records = classify_recent(SENSOR_MODIS, _recent_agg(SENSOR_MODIS, extreme), ref, FULL_COVERAGE)
    assert ref == frozen  # reference object untouched
    for r in records:
        assert r["elevated_threshold"] == frozen[r["month"]]["elevated_threshold"]
        assert r["baseline_median"] == frozen[r["month"]]["baseline_median"]


def test_no_threshold_leakage_unlike_compute_anomalies():
    """compute_anomalies would raise the threshold if recent years were passed in; the new path does not."""
    values = _values()
    cal = _calendar({SENSOR_MODIS: values})
    ref = load_frozen_reference(cal, SENSOR_MODIS)
    rows = [{"period": f"{y}-{m:02d}", "year": y, "month": m, "has_data": True, "sensor": SENSOR_MODIS,
             "occupied_cell_fraction": values[(y, m)] if y < 2025 else 0.99}
            for y in list(REFERENCE_YEARS) + [2025, 2026] for m in range(1, 13)]
    agg = pd.DataFrame(rows)
    leaky = compute_anomalies(agg, compute_seasonal_baseline(agg), elevated_quantile=0.75)
    leaky_thr = leaky[leaky["month"] == 9]["elevated_threshold"].iloc[0]
    assert leaky_thr > ref[9]["elevated_threshold"]  # demonstrates the leak the module avoids


def test_classify_rejects_reference_years_and_mixed_sensors():
    ref = load_frozen_reference(_calendar({SENSOR_MODIS: _values()}), SENSOR_MODIS)
    agg = _recent_agg(SENSOR_MODIS, {})
    with pytest.raises(ValueError, match="reference years"):
        classify_recent(SENSOR_MODIS, pd.concat([agg, agg.assign(year=2024)]), ref, FULL_COVERAGE)
    with pytest.raises(ValueError, match="one sensor"):
        classify_recent(SENSOR_MODIS, pd.concat([agg, agg.assign(sensor=SENSOR_VIIRS)]), ref, FULL_COVERAGE)
    with pytest.raises(ValueError, match="reference year"):
        classify_recent(SENSOR_MODIS, agg, ref, FULL_COVERAGE, years=(2024,))


# --- classification, rank, missing --------------------------------------------

def test_elevated_rule_and_rank():
    values = _values()
    ref = load_frozen_reference(_calendar({SENSOR_MODIS: values}), SENSOR_MODIS)
    top, low = 0.99, 0.0001
    recs = classify_recent(SENSOR_MODIS, _recent_agg(SENSOR_MODIS, {"2025-03": top, "2025-04": low,
                           "2025-05": ref[5]["elevated_threshold"]}), ref, FULL_COVERAGE)
    by = {r["period"]: r for r in recs}
    assert by["2025-03"]["elevated"] is True and by["2025-03"]["historical_rank"] == 1
    assert by["2025-04"]["elevated"] is False and by["2025-04"]["historical_rank"] == 7
    assert by["2025-05"]["elevated"] is False  # equal to threshold is not elevated (strict ">")
    assert by["2025-03"]["n_historical_values"] == 6


def test_equal_cell_counts_tie_despite_json_rounding():
    """Regression: 30/288 unrounded must tie with the stored (rounded) historical 30/288."""
    values = _values()
    values[(2021, 4)] = round(30 / 288, 6)  # 0.104167 as stored in calendar.json
    ref = load_frozen_reference(_calendar({SENSOR_MODIS: values}), SENSOR_MODIS)
    hist = sorted(v for v in ref[4]["historical_values"].values())
    recs = {r["period"]: r for r in classify_recent(SENSOR_MODIS, _recent_agg(SENSOR_MODIS, {"2025-04": 30 / 288}), ref, FULL_COVERAGE)}
    r = recs["2025-04"]
    greater = sum(v > round(30 / 288, 6) for v in hist)
    assert r["n_historical_values_tied"] == 1
    assert r["historical_rank"] == 1 + greater          # tie shares the higher rank
    assert r["historical_rank"] + r["n_historical_values_below"] + r["n_historical_values_tied"] == 7


def test_missing_months_are_null_not_zero():
    ref = load_frozen_reference(_calendar({SENSOR_VIIRS: _values()}), SENSOR_VIIRS)
    agg = _recent_agg(SENSOR_VIIRS, {}, missing=("2026-11", "2026-12", "2025-03"))
    recs = {r["period"]: r for r in classify_recent(SENSOR_VIIRS, agg, ref, FULL_COVERAGE)}
    for p, note in (("2026-11", "outside_downloaded_source_coverage"), ("2026-12", "outside_downloaded_source_coverage"),
                    ("2025-03", "no_detections_after_quality_filtering")):
        r = recs[p]
        assert r["has_data"] is False and r["coverage_note"] == note
        for key in ("occupied_cell_fraction", "elevated", "historical_rank", "anomaly", "n_historical_values_below"):
            assert r[key] is None, (p, key)
    assert recs["2026-11"]["source_type"] is None


def test_partial_source_month_is_not_classified():
    ref = load_frozen_reference(_calendar({SENSOR_MODIS: _values()}), SENSOR_MODIS)
    coverage = {"archive": (date(2025, 1, 1), date(2026, 10, 15))}
    recs = {r["period"]: r for r in classify_recent(SENSOR_MODIS, _recent_agg(SENSOR_MODIS, {}), ref, coverage)}
    assert recs["2026-10"]["coverage_note"] == "partial_month_source_coverage"
    assert recs["2026-10"]["occupied_cell_fraction"] is None and recs["2026-10"]["elevated"] is None


def test_archive_nrt_source_identification():
    assert month_source_type(2026, 7, FULL_COVERAGE) == "archive"
    assert month_source_type(2026, 8, FULL_COVERAGE) == "nrt"
    assert month_source_type(2026, 11, FULL_COVERAGE) is None
    split = {"archive": (date(2025, 1, 1), date(2026, 8, 15)), "nrt": (date(2026, 8, 16), date(2026, 10, 31))}
    assert month_source_type(2026, 8, split) == "archive+nrt"


def test_sensors_are_not_pooled():
    cal = _calendar({SENSOR_MODIS: _values(), SENSOR_VIIRS: _values(scale=2.0)})
    recs = {}
    for s in (SENSOR_MODIS, SENSOR_VIIRS):
        recs[s] = classify_recent(s, _recent_agg(s, {"2025-06": 0.3}), load_frozen_reference(cal, s), FULL_COVERAGE)
        assert {r["sensor"] for r in recs[s]} == {s}
    m, v = recs[SENSOR_MODIS][5], recs[SENSOR_VIIRS][5]
    assert m["occupied_cell_fraction"] == v["occupied_cell_fraction"] == 0.3
    assert m["elevated_threshold"] != v["elevated_threshold"]  # each sensor uses its own reference
    s = summarize(recs)
    assert set(s["by_sensor"]) == {SENSOR_MODIS, SENSOR_VIIRS}


# --- invalid input -------------------------------------------------------------

@pytest.mark.parametrize("mutate,match", [
    (lambda c: c.update(is_fixture=True), "fixture"),
    (lambda c: c.update(primary_grid_convention="A"), "convention"),
    (lambda c: c.update(grid_resolution_deg=0.5), "resolution"),
    (lambda c: c.update(baseline_window={"start": 2019, "end": 2025}), "baseline window"),
    (lambda c: c["sensors"][SENSOR_MODIS]["months"].pop(), "one record per reference year"),
    (lambda c: c["sensors"][SENSOR_MODIS]["months"][0].update(elevated_threshold=0.9), "inconsistent"),
    (lambda c: [m.update(elevated_threshold=0.5) for m in c["sensors"][SENSOR_MODIS]["months"] if m["month"] == 1], "q=0.75"),
])
def test_invalid_reference_is_rejected(mutate, match):
    cal = _calendar({SENSOR_MODIS: _values()})
    mutate(cal)
    with pytest.raises(ValueError, match=match):
        load_frozen_reference(cal, SENSOR_MODIS)


def test_normalize_default_year_window_unchanged(modis_raw_df):
    clean_default, s_default = normalize(modis_raw_df, SENSOR_MODIS)
    clean_explicit, s_explicit = normalize(modis_raw_df, SENSOR_MODIS, year_range=range(2019, 2025))
    pd.testing.assert_frame_equal(clean_default, clean_explicit)
    assert s_default.excluded_outside_years == s_explicit.excluded_outside_years == 1  # the 2018 fixture row


def test_compare_history_detects_changes():
    cal = _calendar({SENSOR_MODIS: _values()})
    rows = [{"period": m["period"], "year": m["year"], "month": m["month"], "has_data": True,
             "occupied_cell_fraction": m["occupied_cell_fraction"], "detection_count": 10, "occupied_cells": 5}
            for m in cal["sensors"][SENSOR_MODIS]["months"]]
    agg = pd.DataFrame(rows)
    assert compare_history(agg, cal, SENSOR_MODIS)["passed"] is True
    agg.loc[0, "detection_count"] = 11
    assert compare_history(agg, cal, SENSOR_MODIS)["passed"] is False


# --- released recent_activity.json --------------------------------------------

@pytest.fixture(scope="module")
def released():
    path = DATA / "recent_activity.json"
    if not path.exists():
        pytest.skip("recent_activity.json not generated")
    return json.loads(path.read_text(encoding="utf-8"))


def test_released_elevated_months_and_intersections(released):
    by = released["summary"]["by_sensor"]
    assert by[SENSOR_MODIS]["2025"]["elevated_months"] == [2, 6, 7]
    assert by[SENSOR_VIIRS]["2025"]["elevated_months"] == [5, 6]
    assert by[SENSOR_MODIS]["2026"]["elevated_months"] == [1, 2, 3, 5, 6, 7, 8, 9, 10]
    assert by[SENSOR_VIIRS]["2026"]["elevated_months"] == [1, 3, 6, 7, 8, 9, 10]
    assert by[SENSOR_MODIS]["2026"]["n_elevated"] == 9 and by[SENSOR_VIIRS]["2026"]["n_elevated"] == 7
    assert released["summary"]["both_sensors_elevated"] == {"2025": [6], "2026": [1, 3, 6, 7, 8, 9, 10]}


def test_released_rank_consistent_with_published_values(released):
    """Rank, below and tied counts recompute exactly from the values in the JSON itself."""
    for sensor, block in released["sensors"].items():
        ref = {r["month"]: r for r in block["reference"]}
        for r in block["records"]:
            if r["occupied_cell_fraction"] is None:
                assert r["historical_rank"] is None and r["n_historical_values_tied"] is None
                continue
            ocf = r["occupied_cell_fraction"]
            hist = [v for v in ref[r["month"]]["historical_values"].values() if v is not None]
            assert r["historical_rank"] == 1 + sum(v > ocf for v in hist), r["period"]
            assert r["n_historical_values_below"] == sum(v < ocf for v in hist), r["period"]
            assert r["n_historical_values_tied"] == sum(v == ocf for v in hist), r["period"]
            assert r["elevated"] == (ocf > r["elevated_threshold"]), r["period"]


def test_released_summary_matches_records(released):
    for sensor, block in released["sensors"].items():
        for year in ("2025", "2026"):
            recs = [r for r in block["records"] if str(r["year"]) == year]
            assert len(recs) == 12
            assert released["summary"]["by_sensor"][sensor][year]["elevated_months"] == [r["month"] for r in recs if r["elevated"] is True]


def test_released_missing_months_and_sources(released):
    for sensor, block in released["sensors"].items():
        recs = {r["period"]: r for r in block["records"]}
        for p in ("2026-11", "2026-12"):
            assert recs[p]["has_data"] is False and recs[p]["occupied_cell_fraction"] is None and recs[p]["elevated"] is None
        assert all(recs[f"2025-{m:02d}"]["source_type"] == "archive" for m in range(1, 13))
    viirs = {r["period"]: r["source_type"] for r in released["sensors"][SENSOR_VIIRS]["records"]}
    modis = {r["period"]: r["source_type"] for r in released["sensors"][SENSOR_MODIS]["records"]}
    assert [viirs[f"2026-{m:02d}"] for m in (7, 8, 9, 10)] == ["archive", "nrt", "nrt", "nrt"]
    assert [modis[f"2026-{m:02d}"] for m in (8, 9, 10)] == ["archive", "nrt", "nrt"]


def test_released_reference_equals_calendar_and_history_unchanged(released):
    calendar = json.loads((DATA / "calendar.json").read_text(encoding="utf-8"))
    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        assert released["historical_reproduction_check"][sensor]["passed"] is True
        ref = load_frozen_reference(calendar, sensor)
        assert released["sensors"][sensor]["reference"] == [ref[m] for m in range(1, 13)]


def test_released_sources_match_manifests(released):
    for sensor in (SENSOR_MODIS, SENSOR_VIIRS):
        manifest = json.loads((ROOT / f"data/manifests/{sensor}_manifest.json").read_text(encoding="utf-8"))
        expected = {e["filename"]: e["sha256"] for e in manifest["files"]}
        got = {s["filename"]: s["sha256"] for s in released["sources"] if s["sensor"] == sensor}
        assert got == expected
    assert released["configuration"]["grid_convention"] == "B"
    assert released["configuration"]["grid_resolution_deg"] == 0.25
    assert released["configuration"]["elevated_quantile"] == 0.75
    assert not released["is_fixture"]


def test_five_production_contracts_unchanged():
    """SHA-256 of the LF-normalized bytes, i.e. the canonical form stored in Git (.gitattributes eol=lf).

    Normalizing line endings makes the check independent of how the working copy was
    checked out (CRLF on Windows with autocrlf, LF elsewhere); any content change still fails.
    """
    expected = {
        "calendar.json": "B18A1483E03252AA", "methodology.json": "3A4947B7517B7881",
        "regions.json": "EDA706AC12797C01", "reliability.json": "D5E911D63864B4F4",
        "sensors.json": "119DA322872248DF",
    }
    for name, prefix in expected.items():
        canonical = (DATA / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical).hexdigest().upper().startswith(prefix), name
