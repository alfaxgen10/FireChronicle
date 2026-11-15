"""
Phase 3 corrections: grid-convention comparison, self-inclusion, and
reliability minimum-evaluable-configuration rule.

SYNTHETIC DATA ONLY.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.aggregate import (
    aggregate_monthly,
    compare_grid_conventions,
    grid_geographic_support,
)
from pipeline.config import (
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    RELIABILITY_MIN_EVALUABLE_CONFIGS,
    SENSOR_MODIS,
)
from pipeline.reliability import compute_stability_summary


def _det(lat, lon, year=2021, month=9):
    return {
        "latitude": lat, "longitude": lon, "year": year, "month": month,
        "acq_datetime_utc": pd.Timestamp(f"{year}-{month:02d}-15"),
        "sensor": SENSOR_MODIS, "frp": 1.0, "brightness": 1.0,
        "daynight": "D", "product_version": "x", "_source_file": "synthetic",
    }


# ---------------------------------------------------------------- grid support
class TestGeographicSupport:
    def test_primary_denominators_unchanged(self):
        """The primary metric definition must not change: 270 and 63 cells."""
        assert grid_geographic_support(resolution=0.25)["convention_a_cells"] == 270
        assert grid_geographic_support(resolution=0.5)["convention_a_cells"] == 63

    def test_convention_b_denominators(self):
        assert grid_geographic_support(resolution=0.25)["convention_b_cells"] == 288
        assert grid_geographic_support(resolution=0.5)["convention_b_cells"] == 72

    def test_uncovered_fractions(self):
        s25 = grid_geographic_support(resolution=0.25)
        s50 = grid_geographic_support(resolution=0.5)
        assert s25["convention_a_bbox_not_covered_fraction"] == pytest.approx(0.038462, abs=1e-5)
        assert s50["convention_a_bbox_not_covered_fraction"] == pytest.approx(0.102564, abs=1e-5)

    def test_convention_b_extends_outside_bbox(self):
        for r in (0.25, 0.5):
            assert grid_geographic_support(resolution=r)["convention_b_area_outside_bbox_sq_deg"] > 0

    def test_primary_aggregate_denominator_is_convention_b(self):
        agg = aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS, 0.25)
        assert agg["total_eligible_cells"].iloc[0] == grid_geographic_support(resolution=0.25)["convention_b_cells"]
        assert (agg["grid_convention"] == "B").all()

    def test_convention_a_denominator_still_available(self):
        agg = aggregate_monthly(pd.DataFrame([_det(-2.5, 103.5)]), SENSOR_MODIS, 0.25, convention="A")
        assert agg["total_eligible_cells"].iloc[0] == 270
        assert (agg["grid_convention"] == "A").all()


class TestConventionComparison:
    def test_primary_ocf_unchanged_by_comparison(self):
        df = pd.DataFrame([_det(-2.5, 103.5), _det(-3.0, 104.0)])
        before = aggregate_monthly(df, SENSOR_MODIS, 0.25)
        compare_grid_conventions(df, SENSOR_MODIS, 0.25)
        after = aggregate_monthly(df, SENSOR_MODIS, 0.25)
        pd.testing.assert_frame_equal(before, after)

    def test_interior_only_detections_differ_only_by_denominator(self):
        df = pd.DataFrame([_det(-2.5, 103.5), _det(-3.0, 104.0)])
        c = compare_grid_conventions(df, SENSOR_MODIS, 0.25)
        r = c[(c.year == 2021) & (c.month == 9)].iloc[0]
        assert r.occupied_cells_a == r.occupied_cells_b == 2
        assert r.ocf_a == pytest.approx(2 / 270)
        assert r.ocf_b == pytest.approx(2 / 288)

    def test_strip_detection_only_counted_by_convention_b(self):
        df = pd.DataFrame([_det(-4.85, 103.5)])
        c = compare_grid_conventions(df, SENSOR_MODIS, 0.25)
        r = c[(c.year == 2021) & (c.month == 9)].iloc[0]
        assert r.occupied_cells_a == 0 and pd.isna(r.ocf_a)
        assert r.occupied_cells_b == 1
        assert bool(r.has_data_differs) is True

    def test_empty_input(self):
        c = compare_grid_conventions(pd.DataFrame(), SENSOR_MODIS, 0.25)
        assert len(c) == 72
        assert c["ocf_b"].isna().all()


# -------------------------------------------------------------- self-inclusion
class TestSelfInclusionExhaustive:
    """
    Distribution-free check (no ties, linear-interpolation quantiles): only the
    rank of the target among the baseline values matters, so every rank is
    enumerated. Results apply ONLY to the n and quantiles listed here.
    """

    @staticmethod
    def _changed_ranks(n_base, q):
        base = np.arange(1, n_base + 1, dtype=float)
        changed = []
        for r in range(n_base + 1):
            t = r + 0.5
            if (t > np.quantile(np.append(base, t), q)) != (t > np.quantile(base, q)):
                changed.append(r)
        return changed

    @pytest.mark.parametrize("q", [0.75, 0.90])
    def test_six_total_observations_no_change(self, q):
        assert self._changed_ranks(5, q) == []

    def test_five_total_observations_can_change_at_q75(self):
        """Counter-example: the 0% result must NOT be generalised to n=5."""
        assert self._changed_ranks(4, 0.75) == [3]


# ------------------------------------------------------------ reliability rule
# Declared configurations in order; MODIS, VIIRS, MODIS, MODIS
_CONFIG_ORDER = [
    ("primary", "MODIS_C61"),
    ("viirs_primary_grid", "VIIRS_J1_C2"),
    ("modis_coarse_grid", "MODIS_C61"),
    ("modis_strict_threshold", "MODIS_C61"),
]


def _rows(period, labels):
    """labels are assigned to the declared configs in _CONFIG_ORDER order."""
    return [{
        "period": period, "year": int(period[:4]), "month": int(period[5:7]),
        "config_name": name, "sensor": sensor, "anomaly_label": lab, "is_fixture": True,
    } for (name, sensor), lab in zip(_CONFIG_ORDER, labels)]


def _label(labels):
    s = compute_stability_summary(pd.DataFrame(_rows("2021-09", labels)))
    return s.iloc[0]


E, N, I = LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED, LABEL_INSUFFICIENT_EVIDENCE


class TestMinimumEvaluableConfigs:
    def test_constant_is_two(self):
        assert RELIABILITY_MIN_EVALUABLE_CONFIGS == 2

    def test_one_elevated_three_insufficient_is_insufficient(self):
        assert _label([E, I, I, I])["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE

    def test_one_not_elevated_three_insufficient_is_insufficient(self):
        assert _label([N, I, I, I])["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE

    def test_one_elevated_one_insufficient_is_insufficient(self):
        # only 2 configs ran; the other 2 declared configs count as not run
        r = _label([E, I])
        assert r["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE
        assert r["n_not_run"] == 3          # 5 declared configs, 2 ran

    def test_two_elevated_two_insufficient_is_consistently_elevated(self):
        assert _label([E, E, I, I])["stability_label"] == LABEL_CONSISTENTLY_ELEVATED

    def test_two_not_elevated_two_insufficient_is_not_elevated(self):
        assert _label([N, N, I, I])["stability_label"] == LABEL_NOT_ELEVATED

    def test_two_disagreeing_evaluable_is_sensitive(self):
        assert _label([E, N, I, I])["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE

    def test_insufficient_never_creates_agreement(self):
        for k in range(0, 8):
            assert _label([I] * (k + 1))["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE

    def test_coverage_fields_reported(self):
        r = _label([E, E, I, I])
        assert r["n_evaluable"] == 2
        assert r["min_evaluable_required"] == 2
        assert r["evaluable_fraction"] == pytest.approx(0.4)   # 2 of 5 declared
        assert r["n_configs_total"] == 5
        assert bool(r["cross_sensor_requirement_met"]) is True

    def test_coverage_fields_for_insufficient_case(self):
        r = _label([E, I, I, I])
        assert r["n_evaluable"] == 1
        assert r["evaluable_fraction"] == pytest.approx(0.2)   # 1 of 5 declared
