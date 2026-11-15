"""
Tests for pipeline.harmonize — MODIS/VIIRS overlap diagnostics.

SYNTHETIC DATA ONLY.  No real NASA observations used.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.harmonize import compute_overlap_diagnostics, diagnostics_to_dict
from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS, YEAR_START, YEAR_END


def _make_agg(sensor, periods_with_data: dict) -> pd.DataFrame:
    """
    Build a minimal aggregated DataFrame.

    Parameters
    ----------
    sensor           : sensor identifier
    periods_with_data: dict mapping "YYYY-MM" -> occupied_cell_fraction value
    """
    rows = []
    for year in range(YEAR_START, YEAR_END + 1):
        for month in range(1, 13):
            period = f"{year:04d}-{month:02d}"
            ocf = periods_with_data.get(period)
            rows.append({
                "period":                  period,
                "year":                    year,
                "month":                   month,
                "sensor":                  sensor,
                "has_data":                ocf is not None,
                "occupied_cell_fraction":  ocf,
                "detection_count":         10 if ocf is not None else 0,
                "total_eligible_cells":    270,
                "occupied_cells":          int(ocf * 270) if ocf is not None else 0,
                "resolution_deg":          0.25,
                "coverage_note":           "observed" if ocf is not None else "no_data",
            })
    return pd.DataFrame(rows)


# Common overlap periods for most tests
_COMMON_PERIODS = {
    "2021-09": 0.10,
    "2021-10": 0.08,
    "2022-09": 0.12,
    "2022-10": 0.07,
    "2023-09": 0.15,
    "2023-10": 0.09,
}


class TestOverlapDiagnostics:
    def test_no_overlap_returns_zero_months(self):
        """Non-overlapping sensors → 0 overlap months."""
        modis_agg = _make_agg(SENSOR_MODIS, {"2021-09": 0.10})
        viirs_agg = _make_agg(SENSOR_VIIRS, {"2022-05": 0.08})
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert diag.n_overlap_months == 0
        assert diag.harmonization_supported is False

    def test_common_months_counted(self):
        """Overlap count equals number of months both sensors have data."""
        modis_data = dict(_COMMON_PERIODS)
        # VIIRS has same 6 months
        viirs_data = {k: v * 1.3 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, modis_data)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert diag.n_overlap_months == 6

    def test_spearman_computed_with_sufficient_data(self):
        viirs_data = {k: v * 1.2 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, _COMMON_PERIODS)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert diag.spearman_rho is not None
        # Perfect rank correlation since viirs = modis * 1.2
        assert abs(diag.spearman_rho) == pytest.approx(1.0, abs=0.01)

    def test_spearman_none_with_too_few_points(self):
        """Fewer than 3 overlap points → Spearman not computed."""
        modis_agg = _make_agg(SENSOR_MODIS, {"2021-09": 0.10, "2021-10": 0.08})
        viirs_agg = _make_agg(SENSOR_VIIRS, {"2021-09": 0.12, "2021-10": 0.09})
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg, min_overlap_months=1)
        assert diag.spearman_rho is None

    def test_harmonization_always_unsupported(self):
        """Harmonization must remain unsupported at this pipeline stage."""
        viirs_data = {k: v * 1.3 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, _COMMON_PERIODS)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert diag.harmonization_supported is False, (
            "Harmonization must not be automatically enabled without validated holdout data"
        )

    def test_ratio_computed_correctly(self):
        modis_data = {"2021-09": 0.10}
        viirs_data = {"2021-09": 0.20}
        modis_agg = _make_agg(SENSOR_MODIS, modis_data)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg, min_overlap_months=1)
        assert diag.mean_ratio_viirs_to_modis == pytest.approx(2.0, rel=0.01)

    def test_ratio_none_when_modis_zero(self):
        """When MODIS OCF is 0, ratio should be None (division by zero avoided)."""
        modis_data = {"2021-09": 0.0}
        viirs_data = {"2021-09": 0.10}
        modis_agg = _make_agg(SENSOR_MODIS, modis_data)
        # mark those rows as has_data=True manually
        modis_agg.loc[modis_agg["period"] == "2021-09", "has_data"] = True
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg, min_overlap_months=1)
        # ratio should be None when modis_ocf == 0
        for entry in diag.detail:
            if entry["period"] == "2021-09":
                assert entry["ratio_viirs_modis"] is None

    def test_limitations_always_present(self):
        """OverlapDiagnostics must always include at least one limitation string."""
        modis_agg = _make_agg(SENSOR_MODIS, {})
        viirs_agg = _make_agg(SENSOR_VIIRS, {})
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert len(diag.limitations) > 0

    def test_detail_contains_expected_fields(self):
        viirs_data = {k: v * 1.2 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, _COMMON_PERIODS)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        for entry in diag.detail:
            for field in ["period", "modis_ocf", "viirs_ocf",
                          "ratio_viirs_modis", "abs_difference"]:
                assert field in entry, f"Missing field {field!r} in detail entry"

    def test_diagnostics_to_dict_serialisable(self):
        """diagnostics_to_dict must produce a JSON-serialisable dict."""
        import json
        viirs_data = {k: v * 1.1 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, _COMMON_PERIODS)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        d = diagnostics_to_dict(diag)
        # Should not raise
        json.dumps(d)

    def test_mad_non_negative(self):
        viirs_data = {k: v * 1.1 for k, v in _COMMON_PERIODS.items()}
        modis_agg = _make_agg(SENSOR_MODIS, _COMMON_PERIODS)
        viirs_agg = _make_agg(SENSOR_VIIRS, viirs_data)
        diag = compute_overlap_diagnostics(modis_agg, viirs_agg)
        assert diag.mean_absolute_difference >= 0
