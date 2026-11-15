"""
Regression tests for reliability configuration registry v2
(approved addition of viirs_coarse_grid; processing version 0.3.0).

Existing configurations and scientific rules must be unchanged; the
minimum-evaluable and cross-sensor requirements must still hold.

SYNTHETIC DATA ONLY.
"""

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.config import (
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    GRID_CONVENTION_PRIMARY,
    GRID_RESOLUTION_DEG_PRIMARY,
    GRID_RESOLUTION_DEG_SENSITIVITY,
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_CROSS_SENSOR,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    RELIABILITY_CONFIG_REGISTRY_HISTORY,
    RELIABILITY_CONFIG_REGISTRY_VERSION,
    RELIABILITY_CONFIGS,
    RELIABILITY_MIN_EVALUABLE_CONFIGS,
    RELIABILITY_MIN_EVALUABLE_PER_SENSOR,
    RELIABILITY_REQUIRED_SENSORS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.reliability import compute_stability_summary, run_reliability_experiment

FRONTEND_DATA = Path(__file__).parent.parent / "web" / "public" / "data"

# Exact registry v1 definitions; these must not change.
V1_EXPECTED = {
    "primary": dict(sensor=SENSOR_MODIS, grid_deg=0.25, elevated_quantile=0.75),
    "viirs_primary_grid": dict(sensor=SENSOR_VIIRS, grid_deg=0.25, elevated_quantile=0.75),
    "modis_coarse_grid": dict(sensor=SENSOR_MODIS, grid_deg=0.5, elevated_quantile=0.75),
    "modis_strict_threshold": dict(sensor=SENSOR_MODIS, grid_deg=0.25, elevated_quantile=0.90),
}

# Declared order in registry v2
CFG = [(name, cfg["sensor"]) for name, cfg in RELIABILITY_CONFIGS.items()]
E, N, I = LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED, LABEL_INSUFFICIENT_EVIDENCE


def _summ(labels, include=None):
    idx = include if include is not None else range(len(labels))
    rows = [{"period": "2021-09", "year": 2021, "month": 9,
             "config_name": CFG[i][0], "sensor": CFG[i][1],
             "anomaly_label": labels[i], "is_fixture": True} for i in idx]
    return compute_stability_summary(pd.DataFrame(rows)).iloc[0]


def _expected(combo, sensors):
    ev = [(c, s) for c, s in zip(combo, sensors) if c != I]
    if len(ev) < RELIABILITY_MIN_EVALUABLE_CONFIGS:
        return LABEL_INSUFFICIENT_EVIDENCE
    for req in RELIABILITY_REQUIRED_SENSORS:
        if sum(1 for _, s in ev if s == req) < RELIABILITY_MIN_EVALUABLE_PER_SENSOR:
            return LABEL_INSUFFICIENT_CROSS_SENSOR
    vals = [c for c, _ in ev]
    if all(v == E for v in vals):
        return LABEL_CONSISTENTLY_ELEVATED
    if all(v == N for v in vals):
        return LABEL_NOT_ELEVATED
    return LABEL_CLASSIFICATION_SENSITIVE


# ------------------------------------------------------------------ registry
class TestRegistry:
    def test_registry_version(self):
        assert RELIABILITY_CONFIG_REGISTRY_VERSION == 2
        assert list(RELIABILITY_CONFIGS) == RELIABILITY_CONFIG_REGISTRY_HISTORY[2]

    def test_v1_configs_present_and_first(self):
        assert list(RELIABILITY_CONFIGS)[:4] == RELIABILITY_CONFIG_REGISTRY_HISTORY[1]

    @pytest.mark.parametrize("name", list(V1_EXPECTED))
    def test_v1_configs_unchanged(self, name):
        cfg = RELIABILITY_CONFIGS[name]
        for k, v in V1_EXPECTED[name].items():
            assert cfg[k] == v, (name, k)
        assert cfg["baseline_start"] == BASELINE_YEAR_START
        assert cfg["baseline_end"] == BASELINE_YEAR_END
        assert cfg["grid_convention"] == GRID_CONVENTION_PRIMARY

    def test_new_viirs_coarse_grid_config(self):
        cfg = RELIABILITY_CONFIGS["viirs_coarse_grid"]
        assert cfg == {
            "sensor": SENSOR_VIIRS,
            "grid_deg": GRID_RESOLUTION_DEG_SENSITIVITY,
            "baseline_start": BASELINE_YEAR_START,
            "baseline_end": BASELINE_YEAR_END,
            "elevated_quantile": 0.75,
            "grid_convention": GRID_CONVENTION_PRIMARY,
        }

    def test_viirs_coarse_mirrors_modis_coarse(self):
        """Only the sensor differs from modis_coarse_grid."""
        a = dict(RELIABILITY_CONFIGS["modis_coarse_grid"])
        b = dict(RELIABILITY_CONFIGS["viirs_coarse_grid"])
        assert a.pop("sensor") == SENSOR_MODIS and b.pop("sensor") == SENSOR_VIIRS
        assert a == b

    def test_sensor_counts(self):
        sensors = [c["sensor"] for c in RELIABILITY_CONFIGS.values()]
        assert sensors.count(SENSOR_MODIS) == 3
        assert sensors.count(SENSOR_VIIRS) == 2

    def test_rules_unchanged(self):
        assert RELIABILITY_MIN_EVALUABLE_CONFIGS == 2
        assert RELIABILITY_MIN_EVALUABLE_PER_SENSOR == 1
        assert tuple(RELIABILITY_REQUIRED_SENSORS) == (SENSOR_MODIS, SENSOR_VIIRS)


# ------------------------------------------------------------- rule enforcement
class TestRulesWithFiveConfigs:
    def test_exhaustive_all_243_combinations(self):
        sensors = [s for _, s in CFG]
        for combo in itertools.product([E, N, I], repeat=len(CFG)):
            r = _summ(list(combo))
            exp = _expected(combo, sensors)
            assert r["stability_label"] == exp, combo
            if exp in (E, N, LABEL_CLASSIFICATION_SENSITIVE):
                assert bool(r["cross_sensor_requirement_met"]) is True
                assert r["modis_n_evaluable"] >= 1 and r["viirs_n_evaluable"] >= 1
            assert r["n_configs_total"] == 5

    def test_two_viirs_alone_not_cross_sensor(self):
        """Two evaluable VIIRS configs meet the overall minimum but not cross-sensor."""
        labels = {"viirs_primary_grid": E, "viirs_coarse_grid": E}
        r = _summ([labels.get(n, I) for n, _ in CFG])
        assert r["stability_label"] == LABEL_INSUFFICIENT_CROSS_SENSOR
        assert r["viirs_label"] == "elevated" and r["viirs_n_evaluable"] == 2
        assert r["sensors_lacking_evaluable_config"] == SENSOR_MODIS

    def test_viirs_coarse_rescues_cross_sensor(self):
        """If viirs_primary_grid is insufficient, viirs_coarse_grid can supply VIIRS evidence."""
        labels = {"primary": E, "viirs_primary_grid": I, "viirs_coarse_grid": E}
        r = _summ([labels.get(n, I) for n, _ in CFG])
        assert r["stability_label"] == LABEL_CONSISTENTLY_ELEVATED
        assert r["viirs_n_evaluable"] == 1

    def test_viirs_configs_disagree(self):
        labels = {"primary": E, "viirs_primary_grid": E, "viirs_coarse_grid": N}
        r = _summ([labels.get(n, I) for n, _ in CFG])
        assert r["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE
        assert r["viirs_label"] == "mixed"

    def test_all_viirs_configs_not_run(self):
        """No VIIRS data: both VIIRS configs not run, never counted as agreement."""
        modis_idx = [i for i, (_, s) in enumerate(CFG) if s == SENSOR_MODIS]
        labels = [E] * len(CFG)
        r = _summ(labels, include=modis_idx)
        assert r["stability_label"] == LABEL_INSUFFICIENT_CROSS_SENSOR
        assert r["n_not_run"] == 2
        assert r["viirs_n_evaluable"] == 0
        assert r["modis_label"] == "elevated"
        assert r["evaluable_fraction"] == pytest.approx(3 / 5)


# ---------------------------------------------------------- experiment run
def _norm(sensor, n=40, seed=0):
    rng = np.random.default_rng(seed)
    years = rng.integers(2019, 2025, n)
    months = rng.integers(1, 13, n)
    return pd.DataFrame({
        "latitude": rng.uniform(-4.9, -1.0, n), "longitude": rng.uniform(101.5, 106.0, n),
        "year": years, "month": months,
        "acq_datetime_utc": pd.to_datetime([f"{y}-{m:02d}-15" for y, m in zip(years, months)]),
        "sensor": sensor, "frp": 1.0, "brightness": 1.0, "daynight": "D",
        "product_version": "x", "_source_file": "synthetic",
    })


class TestExperimentRunsAllConfigs:
    def test_five_configs_run(self):
        out = run_reliability_experiment(
            {SENSOR_MODIS: _norm(SENSOR_MODIS), SENSOR_VIIRS: _norm(SENSOR_VIIRS, seed=1)},
            is_fixture=True)
        assert sorted(out["config_name"].unique()) == sorted(RELIABILITY_CONFIGS)
        viirs_coarse = out[out["config_name"] == "viirs_coarse_grid"]
        assert (viirs_coarse["sensor"] == SENSOR_VIIRS).all()
        assert (viirs_coarse["resolution_deg"] == GRID_RESOLUTION_DEG_SENSITIVITY).all()
        assert (viirs_coarse["grid_convention"] == "B").all()

    def test_missing_viirs_data_skips_both_viirs_configs(self):
        out = run_reliability_experiment({SENSOR_MODIS: _norm(SENSOR_MODIS), SENSOR_VIIRS: None},
                                         is_fixture=True)
        assert set(out["config_name"]) == {"primary", "modis_coarse_grid", "modis_strict_threshold"}
        summ = compute_stability_summary(out)
        assert (summ["n_not_run"] == 2).all()
        assert not summ["stability_label"].isin([E, N, LABEL_CLASSIFICATION_SENSITIVE]).any()


# ------------------------------------------------------------ JSON outputs
def _load(name):
    path = FRONTEND_DATA / name
    if not path.exists():
        pytest.skip(f"{name} not generated")
    return json.loads(path.read_text(encoding="utf-8"))


class TestExportedRegistry:
    def test_reliability_json(self):
        d = _load("reliability.json")
        assert d["config_registry_version"] == 2
        assert list(d["configurations"]) == RELIABILITY_CONFIG_REGISTRY_HISTORY[2]
        assert d["config_registry_history"]["1"] == RELIABILITY_CONFIG_REGISTRY_HISTORY[1]
        for p in d["per_period"]:
            assert p["n_configs_total"] == 5
            assert p["sensor_specific"][SENSOR_MODIS]["n_configs"] == 3
            assert p["sensor_specific"][SENSOR_VIIRS]["n_configs"] == 2

    def test_methodology_json(self):
        d = _load("methodology.json")
        assert d["reliability_config_registry_version"] == 2
        assert "viirs_coarse_grid" in d["reliability_configurations"]
