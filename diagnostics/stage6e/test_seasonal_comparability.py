"""Focused tests for the Stage 6E diagnostic (run: python -m pytest diagnostics/stage6e -q)."""
import json
import statistics
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seasonal_comparability as sc  # noqa: E402

YEARS, MONTHS = sc.YEARS, sc.MONTHS


def make(modis_fn, viirs_fn):
    m = {(y, mo): modis_fn(y, mo) for y in YEARS for mo in MONTHS}
    v = {(y, mo): viirs_fn(y, mo) for y in YEARS for mo in MONTHS}
    return m, v


def calendar_from(m, v):
    def months(d):
        return [{"year": y, "month": mo, "occupied_cell_fraction": d[(y, mo)], "has_data": d[(y, mo)] is not None}
                for (y, mo) in sorted(d)]
    return {"contract_version": "test", "processing_version": "test",
            "sensors": {sc.MODIS: {"months": months(m)}, sc.VIIRS: {"months": months(v)}}}


# --- ratio direction --------------------------------------------------------
def test_ratio_direction_predicts_modis_from_viirs():
    # MODIS = 0.25 * VIIRS exactly -> ratio must be MODIS/VIIRS = 0.25 and predictions exact.
    m, v = make(lambda y, mo: 0.25 * (0.2 + 0.01 * mo + 0.005 * (y - 2019)), lambda y, mo: 0.2 + 0.01 * mo + 0.005 * (y - 2019))
    res = sc.leave_one_year_out(m, v)
    assert sc.seasonal_median_ratio(m, v, [2019, 2020], 3) == pytest.approx(0.25)
    for r in res["records"]:
        assert r["pred_A_seasonal"] == pytest.approx(r["actual_modis"])
        assert r["pred_B_global"] == pytest.approx(r["actual_modis"])
    assert sc.mae(res["records"], "A_seasonal") == pytest.approx(0.0, abs=1e-12)


# --- training / test separation and leakage ------------------------------------
def test_held_out_modis_value_never_used():
    m, v = make(lambda y, mo: 0.10, lambda y, mo: 0.40)
    base = sc.leave_one_year_out(m, v)
    m2 = dict(m); m2[(2022, 5)] = 999.0          # perturb ONE held-out MODIS value
    pert = sc.leave_one_year_out(m2, v)
    b = {(r["year"], r["month"]): r for r in base["records"]}
    p = {(r["year"], r["month"]): r for r in pert["records"]}
    for meth in sc.METHODS:
        assert p[(2022, 5)][f"pred_{meth}"] == pytest.approx(b[(2022, 5)][f"pred_{meth}"]), meth   # its own prediction is unchanged
    # other folds DO see it in training (proves the perturbation is visible when it should be)
    assert p[(2021, 5)]["pred_C_climatology"] != pytest.approx(b[(2021, 5)]["pred_C_climatology"])


def test_training_uses_only_other_years():
    seen = []
    orig = sc.METHODS["A_seasonal"]
    def spy(m, v, tr, y, mo):
        seen.append((y, tuple(tr)))
        assert y not in tr
        assert all(k[0] != y for k in m)           # MODIS training view excludes the held-out year
        return orig(m, v, tr, y, mo)
    sc.METHODS["A_seasonal"] = spy
    try:
        m, v = make(lambda y, mo: 0.1 + 0.001 * y % 7, lambda y, mo: 0.3)
        sc.leave_one_year_out(m, v, methods=["A_seasonal"])
    finally:
        sc.METHODS["A_seasonal"] = orig
    assert {y for y, _ in seen} == set(YEARS)
    assert all(len(tr) == 5 for _, tr in seen)


# --- zero denominators and missing values ----------------------------------------
def test_zero_viirs_denominator_is_excluded_not_divided():
    m, v = make(lambda y, mo: 0.1, lambda y, mo: 0.5)
    for y in YEARS:
        if y != 2024:
            v[(y, 7)] = 0.0                          # all July training denominators are zero
    assert sc.seasonal_median_ratio(m, v, [y for y in YEARS if y != 2024], 7) is None
    res = sc.leave_one_year_out(m, v)
    assert any(e["year"] == 2024 and e["month"] == 7 and "A_seasonal" in e["reason"] for e in res["excluded"])
    assert not any(r["year"] == 2024 and r["month"] == 7 for r in res["records"])


def test_missing_observations_are_excluded_not_zero():
    m, v = make(lambda y, mo: 0.1, lambda y, mo: 0.4)
    m[(2020, 2)] = None
    v[(2021, 3)] = None
    cal = calendar_from(m, v)
    mm, vv = sc.load_observations(cal, sc.MODIS), sc.load_observations(cal, sc.VIIRS)
    assert mm[(2020, 2)] is None and vv[(2021, 3)] is None
    res = sc.leave_one_year_out(mm, vv)
    reasons = {(e["year"], e["month"]): e["reason"] for e in res["excluded"]}
    assert reasons[(2020, 2)] == "MODIS test value missing"
    assert reasons[(2021, 3)] == "VIIRS test value missing"
    # missing values are not treated as zero in training: climatology for Feb in other folds is still 0.1
    feb = [r for r in res["records"] if r["month"] == 2]
    assert all(r["pred_C_climatology"] == pytest.approx(0.1) for r in feb)


def test_has_data_false_is_missing():
    cal = {"sensors": {sc.MODIS: {"months": [{"year": 2019, "month": 1, "occupied_cell_fraction": 0.2, "has_data": False}]}}}
    assert sc.load_observations(cal, sc.MODIS)[(2019, 1)] is None


# --- identical samples, MAE, determinism ---------------------------------------
def test_identical_evaluation_sample_across_methods():
    m, v = make(lambda y, mo: 0.05 + 0.02 * mo, lambda y, mo: 0.3 + 0.01 * mo)
    m[(2023, 4)] = None
    res = sc.leave_one_year_out(m, v)
    for r in res["records"]:
        for meth in sc.METHODS:
            assert f"pred_{meth}" in r and f"abserr_{meth}" in r
    assert len(res["records"]) + len(res["excluded"]) == len(YEARS) * len(MONTHS)


def test_mae_is_mean_absolute_error():
    recs = [{"abserr_X": 0.1}, {"abserr_X": 0.3}, {"abserr_X": 0.2}]
    assert sc.mae(recs, "X") == pytest.approx(0.2)
    m, v = make(lambda y, mo: 0.1 * (1 + (y % 3)), lambda y, mo: 0.5)
    res = sc.leave_one_year_out(m, v, methods=["C_climatology"])
    manual = statistics.fmean(abs(statistics.fmean(m[(yy, r["month"])] for yy in YEARS if yy != r["year"]) - r["actual_modis"])
                              for r in res["records"])
    assert sc.mae(res["records"], "C_climatology") == pytest.approx(manual)


def test_deterministic(tmp_path):
    m, v = make(lambda y, mo: 0.03 * mo + 0.002 * y % 5, lambda y, mo: 0.2 + 0.03 * mo)
    cal = tmp_path / "calendar.json"
    cal.write_text(json.dumps(calendar_from(m, v)), encoding="utf-8")
    r1 = sc.run(cal, tmp_path / "o1"); r2 = sc.run(cal, tmp_path / "o2")
    assert r1["summary"] == r2["summary"] and r1["robustness"] == r2["robustness"]
    assert (tmp_path / "o1" / "results.json").read_bytes() == (tmp_path / "o2" / "results.json").read_bytes()


def test_released_calendar_is_read_only(tmp_path):
    if not sc.DEFAULT_CALENDAR.exists():
        pytest.skip("released calendar.json not present")
    before = sc.DEFAULT_CALENDAR.read_bytes()
    sc.run(sc.DEFAULT_CALENDAR, tmp_path / "out")
    assert sc.DEFAULT_CALENDAR.read_bytes() == before
