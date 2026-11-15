"""
Regression tests for the approved final scientific decisions (processing 0.2.0):

1. Convention B (every cell intersecting the bbox) is the primary grid;
   Convention A is retained as a sensitivity comparison.
2. Cross-sensor agreement labels require >= 2 evaluable configurations
   including >= 1 MODIS and >= 1 VIIRS.  Otherwise insufficient cross-sensor
   evidence is reported and sensor-specific findings are retained.

SYNTHETIC DATA ONLY.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pipeline.aggregate import (
    aggregate_monthly,
    build_grid,
    compare_grid_conventions,
    grid_cell_counts,
)
from pipeline.config import (
    BBOX,
    GRID_CONVENTION_PRIMARY,
    GRID_CONVENTION_SENSITIVITY,
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_CROSS_SENSOR,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    PROCESSING_VERSION,
    RELIABILITY_CONFIGS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.reliability import compute_stability_summary

FRONTEND_DATA = Path(__file__).parent.parent / "web" / "public" / "data"
LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = BBOX


def _det(lat, lon, year=2021, month=9):
    return {
        "latitude": lat, "longitude": lon, "year": year, "month": month,
        "acq_datetime_utc": pd.Timestamp(f"{year}-{month:02d}-15"),
        "sensor": SENSOR_MODIS, "frp": 1.0, "brightness": 1.0,
        "daynight": "D", "product_version": "x", "_source_file": "synthetic",
    }


def _sep(agg):
    return agg[(agg["year"] == 2021) & (agg["month"] == 9)].iloc[0]


# =============================================================== 1. grid
class TestPrimaryConventionIsB:
    def test_config_constants(self):
        assert GRID_CONVENTION_PRIMARY == "B"
        assert GRID_CONVENTION_SENSITIVITY == "A"

    def test_processing_version_bumped(self):
        assert PROCESSING_VERSION == "0.3.0"

    def test_default_aggregation_uses_b(self):
        agg = aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS)
        assert (agg["grid_convention"] == "B").all()
        assert agg["total_eligible_cells"].iloc[0] == 288

    def test_unknown_convention_rejected(self):
        with pytest.raises(ValueError):
            aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS, convention="C")
        with pytest.raises(ValueError):
            build_grid(BBOX, 0.25, "C")

    def test_all_reliability_configs_declare_convention_b(self):
        for name, cfg in RELIABILITY_CONFIGS.items():
            assert cfg.get("grid_convention") == "B", name


class TestCellCounts:
    @pytest.mark.parametrize("res,eligible,interior,partial", [
        (0.25, 288, 270, 18),
        (0.5, 72, 63, 9),
    ])
    def test_convention_b_counts(self, res, eligible, interior, partial):
        c = grid_cell_counts(resolution=res, convention="B")
        assert (c["eligible_cells"], c["fully_interior_cells"], c["partial_boundary_cells"]) == (
            eligible, interior, partial)

    @pytest.mark.parametrize("res,eligible", [(0.25, 270), (0.5, 63)])
    def test_convention_a_counts(self, res, eligible):
        c = grid_cell_counts(resolution=res, convention="A")
        assert c["eligible_cells"] == eligible
        assert c["partial_boundary_cells"] == 0

    def test_partial_boundary_cells_are_exactly_the_southern_row(self):
        grid = build_grid(BBOX, 0.25, "B")
        partial = grid[grid["cell_lat"] < LAT_MIN]
        assert len(partial) == 18
        assert set(partial["cell_lat"].round(8)) == {-5.0}

    def test_every_b_cell_intersects_bbox(self):
        for res in (0.25, 0.5):
            g = build_grid(BBOX, res, "B")
            assert ((g["cell_lon"] < LON_MAX) & (g["cell_lon"] + res > LON_MIN) &
                    (g["cell_lat"] < LAT_MAX) & (g["cell_lat"] + res > LAT_MIN)).all()

    def test_no_intersecting_cell_missing_from_b(self):
        """Exhaustive: every cell on the global grid that intersects the bbox is in B."""
        for res in (0.25, 0.5):
            g = build_grid(BBOX, res, "B")
            have = set(zip(g["cell_lon"].round(8), g["cell_lat"].round(8)))
            for i in range(int(np.floor(LON_MIN / res)) - 2, int(np.ceil(LON_MAX / res)) + 2):
                for j in range(int(np.floor(LAT_MIN / res)) - 2, int(np.ceil(LAT_MAX / res)) + 2):
                    lo, la = i * res, j * res
                    intersects = lo < LON_MAX and lo + res > LON_MIN and la < LAT_MAX and la + res > LAT_MIN
                    assert intersects == ((round(lo, 8), round(la, 8)) in have), (res, lo, la)


class TestBoundaryInclusionConventionB:
    """Every in-bounds observation must be included under the primary convention."""

    @pytest.mark.parametrize("lat,lon", [
        (LAT_MIN, LON_MIN), (LAT_MIN, LON_MAX), (LAT_MAX, LON_MIN), (LAT_MAX, LON_MAX),  # corners
        (LAT_MIN, 103.5), (LAT_MAX, 103.5), (-2.5, LON_MIN), (-2.5, LON_MAX),             # edges
        (-4.85, 103.5), (-4.899, 105.999),                                                 # southern strip
    ])
    @pytest.mark.parametrize("res", [0.25, 0.5])
    def test_in_bounds_point_counted(self, lat, lon, res):
        r = _sep(aggregate_monthly(pd.DataFrame([_det(lat, lon)]), SENSOR_MODIS, res, convention="B"))
        assert r["detection_count"] == 1
        assert r["occupied_cells"] == 1
        assert bool(r["has_data"]) is True

    @pytest.mark.parametrize("lat,lon", [
        (LAT_MIN - 0.001, 103.5), (LAT_MAX + 0.001, 103.5),
        (-2.5, LON_MIN - 0.001), (-2.5, LON_MAX + 0.001),
    ])
    def test_out_of_bounds_point_excluded(self, lat, lon):
        r = _sep(aggregate_monthly(pd.DataFrame([_det(lat, lon)]), SENSOR_MODIS, convention="B"))
        assert r["detection_count"] == 0
        assert r["occupied_cells"] == 0

    def test_random_in_bounds_points_all_counted(self):
        """No in-bounds detection may fall outside an eligible B cell."""
        rng = np.random.default_rng(1)
        n = 2000
        df = pd.DataFrame([_det(la, lo) for la, lo in zip(
            rng.uniform(LAT_MIN, LAT_MAX, n), rng.uniform(LON_MIN, LON_MAX, n))])
        for res in (0.25, 0.5):
            r = _sep(aggregate_monthly(df, SENSOR_MODIS, res, convention="B"))
            assert r["detection_count"] == n
            # every unique cell of the points is eligible
            cells = {(np.floor(la / res) * res, np.floor(lo / res) * res)
                     for la, lo in zip(df["latitude"], df["longitude"])}
            assert r["occupied_cells"] == len(cells)

    def test_strip_detection_flagged_as_partial_boundary(self):
        r = _sep(aggregate_monthly(pd.DataFrame([_det(-4.85, 103.5)]), SENSOR_MODIS, convention="B"))
        assert r["partial_cell_detections"] == 1
        assert r["partial_boundary_cells"] == 18

    def test_interior_detection_not_flagged_partial(self):
        r = _sep(aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS, convention="B"))
        assert r["partial_cell_detections"] == 0

    def test_ocf_is_cell_count_ratio_not_area(self):
        """A partial boundary cell counts as a whole cell (weight 1)."""
        strip = _sep(aggregate_monthly(pd.DataFrame([_det(-4.85, 103.5)]), SENSOR_MODIS, convention="B"))
        inner = _sep(aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS, convention="B"))
        assert strip["occupied_cell_fraction"] == inner["occupied_cell_fraction"] == pytest.approx(1 / 288)


class TestConventionComparisonRetained:
    def test_b_and_a_side_by_side(self):
        df = pd.DataFrame([_det(-4.85, 103.5), _det(-2.5, 103.5)])
        r = _sep(compare_grid_conventions(df, SENSOR_MODIS, 0.25))
        assert (r["occupied_cells_b"], r["denominator_b"]) == (2, 288)
        assert (r["occupied_cells_a"], r["denominator_a"]) == (1, 270)
        assert r["ocf_b"] == pytest.approx(2 / 288)
        assert r["ocf_a"] == pytest.approx(1 / 270)

    def test_strip_only_month_differs(self):
        r = _sep(compare_grid_conventions(pd.DataFrame([_det(-4.85, 103.5)]), SENSOR_MODIS))
        assert bool(r["has_data_differs"]) is True
        assert pd.isna(r["ocf_a"]) and r["ocf_b"] == pytest.approx(1 / 288)


# ======================================================= 2. cross-sensor rule
E, N, I = LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED, LABEL_INSUFFICIENT_EVIDENCE
# Registry v1 configurations in declared order.  The tests below give results
# for these four only; the fifth declared config (viirs_coarse_grid) is then
# "not run", which must never count as agreement.  Registry v2 behaviour is
# tested in tests/test_registry_v2.py.
CFG = [("primary", SENSOR_MODIS), ("viirs_primary_grid", SENSOR_VIIRS),
       ("modis_coarse_grid", SENSOR_MODIS), ("modis_strict_threshold", SENSOR_MODIS)]


def _summ(labels, include=None):
    """labels by declared config order; include = indices of configs that ran."""
    idx = include if include is not None else range(len(labels))
    rows = [{"period": "2021-09", "year": 2021, "month": 9,
             "config_name": CFG[i][0], "sensor": CFG[i][1],
             "anomaly_label": labels[i], "is_fixture": True} for i in idx]
    return compute_stability_summary(pd.DataFrame(rows)).iloc[0]


class TestCrossSensorRule:
    def test_all_agree_elevated(self):
        r = _summ([E, E, E, E])
        assert r["stability_label"] == LABEL_CONSISTENTLY_ELEVATED
        assert bool(r["cross_sensor_requirement_met"]) is True

    def test_all_agree_not_elevated(self):
        assert _summ([N, N, N, N])["stability_label"] == LABEL_NOT_ELEVATED

    def test_cross_sensor_disagreement_is_sensitive(self):
        r = _summ([E, N, E, E])
        assert r["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE
        assert r["modis_label"] == "elevated" and r["viirs_label"] == "not_elevated"

    def test_three_modis_agree_but_viirs_insufficient(self):
        """MODIS-only agreement is NOT cross-sensor agreement."""
        r = _summ([E, I, E, E])
        assert r["stability_label"] == LABEL_INSUFFICIENT_CROSS_SENSOR
        assert r["sensors_lacking_evaluable_config"] == SENSOR_VIIRS
        # sensor-specific MODIS finding retained
        assert r["modis_label"] == "elevated"
        assert r["modis_n_evaluable"] == 3
        assert r["viirs_label"] == "insufficient_evidence"

    def test_viirs_config_did_not_run(self):
        """Missing VIIRS data: config absent, counted as not run, not as agreement."""
        r = _summ([E, None, E, E], include=[0, 2, 3])
        assert r["stability_label"] == LABEL_INSUFFICIENT_CROSS_SENSOR
        assert r["n_not_run"] == 2          # viirs_primary_grid + viirs_coarse_grid
        assert r["n_configs_total"] == 5
        assert r["evaluable_fraction"] == pytest.approx(0.6)

    def test_all_modis_insufficient_viirs_elevated(self):
        r = _summ([I, E, I, I])
        # only one evaluable overall -> below the overall minimum
        assert r["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE
        assert r["viirs_label"] == "elevated"
        assert r["modis_label"] == "insufficient_evidence"

    def test_one_modis_one_viirs_is_enough(self):
        r = _summ([E, E, I, I])
        assert r["stability_label"] == LABEL_CONSISTENTLY_ELEVATED

    def test_modis_mixed_viirs_elevated_is_sensitive(self):
        r = _summ([E, E, N, I])
        assert r["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE
        assert r["modis_label"] == "mixed"

    def test_sensor_specific_labels_differ_from_cross_sensor_labels(self):
        """Sensor-specific 'elevated' must never equal the cross-sensor label string."""
        r = _summ([E, I, E, E])
        assert r["modis_label"] != LABEL_CONSISTENTLY_ELEVATED

    @pytest.mark.parametrize("labels", [
        [I, I, I, I], [E, I, I, I], [N, I, I, I], [I, E, I, I], [E, I, E, I], [N, I, N, N],
    ])
    def test_no_agreement_label_without_both_sensors(self, labels):
        r = _summ(labels)
        agreement = {LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED, LABEL_CLASSIFICATION_SENSITIVE}
        modis_ok = r["modis_n_evaluable"] >= 1
        viirs_ok = r["viirs_n_evaluable"] >= 1
        if not (modis_ok and viirs_ok):
            assert r["stability_label"] not in agreement

    def test_exhaustive_rule(self):
        """Every combination of the 3 possible results across 4 configs follows the rule."""
        import itertools
        agreement = {LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED, LABEL_CLASSIFICATION_SENSITIVE}
        for combo in itertools.product([E, N, I], repeat=4):
            r = _summ(list(combo))
            ev = [c for c in combo if c != I]
            modis_ev = sum(1 for k, c in enumerate(combo) if c != I and CFG[k][1] == SENSOR_MODIS)
            viirs_ev = sum(1 for k, c in enumerate(combo) if c != I and CFG[k][1] == SENSOR_VIIRS)
            if len(ev) < 2:
                expected = LABEL_INSUFFICIENT_EVIDENCE
            elif modis_ev < 1 or viirs_ev < 1:
                expected = LABEL_INSUFFICIENT_CROSS_SENSOR
            elif all(c == E for c in ev):
                expected = LABEL_CONSISTENTLY_ELEVATED
            elif all(c == N for c in ev):
                expected = LABEL_NOT_ELEVATED
            else:
                expected = LABEL_CLASSIFICATION_SENSITIVE
            assert r["stability_label"] == expected, combo
            if expected in agreement:
                assert bool(r["cross_sensor_requirement_met"]) is True


# ============================================================ 3. JSON outputs
def _load(name):
    path = FRONTEND_DATA / name
    if not path.exists():
        pytest.skip(f"{name} not generated")
    return json.loads(path.read_text(encoding="utf-8"))


class TestExportedContracts:
    def test_versions(self):
        for f in ("regions.json", "calendar.json", "sensors.json", "reliability.json", "methodology.json"):
            d = _load(f)
            assert d["processing_version"] == "0.3.0", f
            assert d["contract_version"] == "1.2.0", f

    def test_calendar_distinguishes_metric_definitions(self):
        d = _load("calendar.json")
        assert d["primary_grid_convention"] == "B"
        assert d["sensitivity_grid_convention"] == "A"
        assert set(d["metric_definitions"]) == {"A", "B"}
        assert "not area-weighted" in d["area_caveat"]
        assert d["grid_cells"]["B"]["eligible_cells"] == 288
        assert d["grid_cells"]["B"]["partial_boundary_cells"] == 18
        assert d["grid_cells"]["A"]["eligible_cells"] == 270
        for sensor in d["sensors"].values():
            for m in sensor["months"]:
                assert m["grid_convention"] == "B"
                assert m["total_eligible_cells"] == 288
                assert "occupied_cell_fraction_convention_a" in m
                if not m["has_data"]:
                    assert m["occupied_cell_fraction"] is None

    def test_calendar_keeps_v1_fields(self):
        """Contract 1.1.0 is additive: every 1.0.0 month field is still present."""
        v1 = {"period", "year", "month", "detection_count", "occupied_cell_fraction", "has_data",
              "coverage_note", "baseline_median", "anomaly", "is_elevated", "anomaly_label",
              "elevated_threshold"}
        d = _load("calendar.json")
        for sensor in d["sensors"].values():
            for m in sensor["months"]:
                assert v1 <= set(m)

    def test_modis_sensor_labels_do_not_claim_collection_6_1_only(self):
        calendar = _load("calendar.json")
        sensors = _load("sensors.json")
        assert calendar["sensors"][SENSOR_MODIS]["label"] == "MODIS Terra / Aqua"
        assert sensors["sensor_metadata"][SENSOR_MODIS]["label"] == "MODIS Terra / Aqua"

    def test_reliability_cross_sensor_fields(self):
        d = _load("reliability.json")
        assert LABEL_INSUFFICIENT_CROSS_SENSOR in d["stability_labels"]
        rule = d["cross_sensor_rule"]
        assert rule["required_sensors"] == [SENSOR_MODIS, SENSOR_VIIRS]
        assert rule["min_evaluable_per_sensor"] == 1
        for p in d["per_period"]:
            assert set(p["sensor_specific"]) == {SENSOR_MODIS, SENSOR_VIIRS}
            if p["stability_label"] in (E, N, LABEL_CLASSIFICATION_SENSITIVE):
                assert p["cross_sensor_requirement_met"] is True
                assert p["sensor_specific"][SENSOR_MODIS]["n_evaluable"] >= 1
                assert p["sensor_specific"][SENSOR_VIIRS]["n_evaluable"] >= 1

    def test_methodology_primary_convention_b(self):
        d = _load("methodology.json")
        assert d["geographic_support"]["primary_convention"].startswith("B")
        assert d["index_definition"]["not_area_weighted"] is True
