#!/usr/bin/env python
"""
Stage 6E — cross-validated seasonal comparability diagnostic (standalone; NOT part of the release).

Research question
-----------------
Does a calendar-month-specific ratio between MODIS and VIIRS occupied-cell fractions,
estimated on training years only, predict held-out MODIS monthly values better than
(B) one global ratio and (C) MODIS climatology?

This is a predictive diagnostic. It is NOT a calibrated sensor product, a validated
harmonization algorithm, sensor fusion or a sensor-independent activity measure.

Data
----
Released ``web/public/data/calendar.json`` (read only): for each sensor, monthly
``occupied_cell_fraction`` (Convention B, 0.25 degree, 288 eligible cells). In the
release a month with zero occupied cells is stored as ``null`` (aggregate.py), so a
null value is treated as MISSING, never as zero.

Methods (predict MODIS from VIIRS; ratio = MODIS / VIIRS)
--------------------------------------------------------
For held-out year Y and calendar month m, training data are all years != Y.

Primary definitions:
  A  seasonal  : r_m = median over training years of MODIS(y,m) / VIIRS(y,m);   pred = r_m * VIIRS(Y,m)
  B  global    : r   = median over all training months of MODIS / VIIRS;         pred = r   * VIIRS(Y,m)
  C  climatology: c_m = mean over training years of MODIS(y,m);                   pred = c_m
Sensitivity variants:
  A_rom / B_rom: ratio of means  (sum MODIS / sum VIIRS) instead of median of ratios
  C_median     : median instead of mean (the definition used by the preliminary audit check)

Eligibility: a test observation is evaluated only if MODIS(Y,m) and VIIRS(Y,m) are present
and every method in the comparison can produce a prediction; the same eligible set is used
for all methods. Training pairs need both sensors present and VIIRS > 0 for ratio terms.

Usage
-----
    python diagnostics/stage6e/seasonal_comparability.py [--calendar PATH] [--out DIR]

Deterministic: no randomness. Writes only to --out (default: diagnostics/stage6e/results).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Callable, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CALENDAR = ROOT / "web" / "public" / "data" / "calendar.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "results"
MODIS, VIIRS = "MODIS_C61", "VIIRS_J1_C2"
YEARS = tuple(range(2019, 2025))
MONTHS = tuple(range(1, 13))

Obs = dict[tuple[int, int], Optional[float]]


# --------------------------------------------------------------------------- data
def load_observations(calendar: dict, sensor: str, years: Iterable[int] = YEARS) -> Obs:
    """{(year, month): occupied_cell_fraction or None}. Null / has_data=false -> None (missing)."""
    years = set(years)
    out: Obs = {}
    for rec in calendar["sensors"][sensor]["months"]:
        if rec["year"] not in years:
            continue
        v = rec.get("occupied_cell_fraction")
        out[(int(rec["year"]), int(rec["month"]))] = float(v) if (v is not None and rec.get("has_data", True)) else None
    return out


def present(x: Optional[float]) -> bool:
    return x is not None


# --------------------------------------------------------------------------- estimators (training data only)
def _ratios(modis: Obs, viirs: Obs, keys: Iterable[tuple[int, int]]) -> list[float]:
    """MODIS/VIIRS for keys where both are present and VIIRS > 0 (zero denominators skipped)."""
    return [modis[k] / viirs[k] for k in keys
            if present(modis.get(k)) and present(viirs.get(k)) and viirs[k] > 0]


def seasonal_median_ratio(modis: Obs, viirs: Obs, train_years: Iterable[int], month: int) -> Optional[float]:
    r = _ratios(modis, viirs, [(y, month) for y in train_years])
    return statistics.median(r) if r else None


def seasonal_ratio_of_means(modis: Obs, viirs: Obs, train_years: Iterable[int], month: int) -> Optional[float]:
    keys = [(y, month) for y in train_years if present(modis.get((y, month))) and present(viirs.get((y, month)))]
    den = sum(viirs[k] for k in keys)
    return (sum(modis[k] for k in keys) / den) if keys and den > 0 else None


def global_median_ratio(modis: Obs, viirs: Obs, train_years: Iterable[int]) -> Optional[float]:
    r = _ratios(modis, viirs, [(y, m) for y in train_years for m in MONTHS])
    return statistics.median(r) if r else None


def global_ratio_of_means(modis: Obs, viirs: Obs, train_years: Iterable[int]) -> Optional[float]:
    keys = [(y, m) for y in train_years for m in MONTHS if present(modis.get((y, m))) and present(viirs.get((y, m)))]
    den = sum(viirs[k] for k in keys)
    return (sum(modis[k] for k in keys) / den) if keys and den > 0 else None


def climatology_mean(modis: Obs, train_years: Iterable[int], month: int) -> Optional[float]:
    v = [modis[(y, month)] for y in train_years if present(modis.get((y, month)))]
    return statistics.fmean(v) if v else None


def climatology_median(modis: Obs, train_years: Iterable[int], month: int) -> Optional[float]:
    v = [modis[(y, month)] for y in train_years if present(modis.get((y, month)))]
    return statistics.median(v) if v else None


METHODS: dict[str, Callable[[Obs, Obs, list[int], int, int], Optional[float]]] = {
    # name -> f(modis, viirs, train_years, test_year, month) -> prediction or None
    "A_seasonal":   lambda m, v, tr, y, mo: _scale(seasonal_median_ratio(m, v, tr, mo), v.get((y, mo))),
    "B_global":     lambda m, v, tr, y, mo: _scale(global_median_ratio(m, v, tr), v.get((y, mo))),
    "C_climatology": lambda m, v, tr, y, mo: climatology_mean(m, tr, mo),
    "A_seasonal_rom": lambda m, v, tr, y, mo: _scale(seasonal_ratio_of_means(m, v, tr, mo), v.get((y, mo))),
    "B_global_rom":   lambda m, v, tr, y, mo: _scale(global_ratio_of_means(m, v, tr), v.get((y, mo))),
    "C_climatology_median": lambda m, v, tr, y, mo: climatology_median(m, tr, mo),
}
PRIMARY = ("A_seasonal", "B_global", "C_climatology")


def _scale(ratio: Optional[float], viirs_value: Optional[float]) -> Optional[float]:
    return None if (ratio is None or viirs_value is None) else ratio * viirs_value


# --------------------------------------------------------------------------- validation
def leave_one_year_out(modis: Obs, viirs: Obs, years: Iterable[int] = YEARS,
                       methods: Iterable[str] = tuple(METHODS)) -> dict:
    """Strict LOYO. Returns per-observation records (identical eligible set for all methods) and exclusions."""
    years = list(years)
    methods = list(methods)
    records, excluded = [], []
    for test_year in years:
        train = [y for y in years if y != test_year]
        for month in MONTHS:
            k = (test_year, month)
            actual, vx = modis.get(k), viirs.get(k)
            if not present(actual):
                excluded.append({"year": test_year, "month": month, "reason": "MODIS test value missing"}); continue
            if not present(vx):
                excluded.append({"year": test_year, "month": month, "reason": "VIIRS test value missing"}); continue
            # Training views exclude the held-out year entirely (defence in depth: estimators only see `train`).
            m_train = {kk: vv for kk, vv in modis.items() if kk[0] != test_year}
            preds = {name: METHODS[name](m_train, viirs, train, test_year, month) for name in methods}
            missing = [n for n, p in preds.items() if p is None]
            if missing:
                excluded.append({"year": test_year, "month": month, "reason": f"no training estimate for {missing}"}); continue
            records.append({"year": test_year, "month": month, "actual_modis": actual, "viirs": vx,
                            **{f"pred_{n}": p for n, p in preds.items()},
                            **{f"abserr_{n}": abs(p - actual) for n, p in preds.items()}})
    return {"records": records, "excluded": excluded, "methods": methods, "years": years}


def mae(records: list[dict], method: str) -> Optional[float]:
    e = [r[f"abserr_{method}"] for r in records]
    return statistics.fmean(e) if e else None


def summarize(result: dict) -> dict:
    recs, methods = result["records"], result["methods"]
    by_year = {y: {m: mae([r for r in recs if r["year"] == y], m) for m in methods} for y in result["years"]}
    by_month = {mo: {m: mae([r for r in recs if r["month"] == mo], m) for m in methods} for mo in MONTHS}
    return {"n_evaluated": len(recs), "n_excluded": len(result["excluded"]), "excluded": result["excluded"],
            "mae": {m: mae(recs, m) for m in methods}, "mae_by_year": by_year, "mae_by_month": by_month}


# --------------------------------------------------------------------------- robustness
def robustness(modis: Obs, viirs: Obs, result: dict) -> dict:
    recs = result["records"]
    A, B, C = PRIMARY
    out: dict = {}
    # 1. fold consistency
    folds = {y: {m: mae([r for r in recs if r["year"] == y], m) for m in PRIMARY} for y in result["years"]}
    out["folds_A_better_than_C"] = sum(1 for f in folds.values() if f[A] < f[C])
    out["folds_A_better_than_B"] = sum(1 for f in folds.values() if f[A] < f[B])
    out["folds_B_better_than_C"] = sum(1 for f in folds.values() if f[B] < f[C])
    # 2. observation-level wins
    out["obs_A_better_than_C"] = sum(1 for r in recs if r[f"abserr_{A}"] < r[f"abserr_{C}"])
    out["obs_A_better_than_B"] = sum(1 for r in recs if r[f"abserr_{A}"] < r[f"abserr_{B}"])
    # 3. summary MAE with each held-out fold dropped from the average
    out["mae_without_fold"] = {y: {m: mae([r for r in recs if r["year"] != y], m) for m in PRIMARY} for y in result["years"]}
    # 4. full re-run with one year removed from the whole dataset (5-year LOYO, 4 training years)
    out["rerun_without_year"] = {}
    for drop in result["years"]:
        sub = leave_one_year_out(modis, viirs, [y for y in result["years"] if y != drop], PRIMARY)
        out["rerun_without_year"][drop] = {m: mae(sub["records"], m) for m in PRIMARY}
    # 5. month dominance: share of total absolute error and of the A-vs-C improvement
    tot = {m: sum(r[f"abserr_{m}"] for r in recs) for m in PRIMARY}
    gain = {mo: sum(r[f"abserr_{C}"] - r[f"abserr_{A}"] for r in recs if r["month"] == mo) for mo in MONTHS}
    total_gain = sum(gain.values())
    out["error_share_by_month_A"] = {mo: sum(r[f"abserr_{A}"] for r in recs if r["month"] == mo) / tot[A] for mo in MONTHS}
    out["improvement_A_vs_C_by_month"] = gain
    out["improvement_A_vs_C_total"] = total_gain
    top3 = sorted(gain, key=gain.get, reverse=True)[:3]
    out["improvement_top3_months"] = top3
    out["improvement_top3_share"] = (sum(gain[m] for m in top3) / total_gain) if total_gain else None
    # 6. stability of the seasonal ratio across folds (each fold uses 5 years)
    stab = {}
    for mo in MONTHS:
        est = [seasonal_median_ratio(modis, viirs, [y for y in result["years"] if y != t], mo) for t in result["years"]]
        raw = [modis[(y, mo)] / viirs[(y, mo)] for y in result["years"] if present(modis.get((y, mo))) and present(viirs.get((y, mo))) and viirs[(y, mo)] > 0]
        est = [e for e in est if e is not None]
        stab[mo] = {"n_training_ratios": len(raw) - 1, "yearly_ratio_min": min(raw), "yearly_ratio_max": max(raw),
                    "fold_estimate_min": min(est), "fold_estimate_max": max(est),
                    "fold_estimate_rel_range": (max(est) - min(est)) / statistics.fmean(est)}
    out["seasonal_ratio_stability"] = stab
    return out


# --------------------------------------------------------------------------- CLI
def run(calendar_path: Path, out_dir: Path) -> dict:
    raw = calendar_path.read_bytes()
    calendar = json.loads(raw)
    modis, viirs = load_observations(calendar, MODIS), load_observations(calendar, VIIRS)
    result = leave_one_year_out(modis, viirs)
    summary = summarize(result)
    rob = robustness(modis, viirs, result)
    report = {
        "diagnostic": "Stage 6E seasonal comparability (predictive diagnostic only; not calibration or fusion)",
        "input": {"path": str(calendar_path.relative_to(ROOT)) if calendar_path.is_relative_to(ROOT) else str(calendar_path),
                  "sha256": hashlib.sha256(raw).hexdigest(),
                  "sha256_lf_normalized": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
                  "contract_version": calendar.get("contract_version"), "processing_version": calendar.get("processing_version")},
        "definition": {"target": "MODIS occupied_cell_fraction", "predictor": "VIIRS occupied_cell_fraction",
                       "ratio": "MODIS / VIIRS", "years": list(YEARS), "validation": "leave-one-year-out"},
        "summary": summary, "robustness": rob,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with open(out_dir / "predictions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(result["records"][0].keys()))
        w.writeheader()
        for r in result["records"]:
            w.writerow({k: (f"{v:.6f}" if isinstance(v, float) else v) for k, v in r.items()})
    return report


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = p.parse_args(argv)
    rep = run(a.calendar.resolve(), a.out.resolve())
    s = rep["summary"]
    print(f"evaluated {s['n_evaluated']} | excluded {s['n_excluded']}")
    for m, v in s["mae"].items():
        print(f"  MAE {m:22} {v:.6f}")


if __name__ == "__main__":
    main()
