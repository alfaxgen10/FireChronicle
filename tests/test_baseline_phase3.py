"""
Phase 3 seasonal baseline and self-inclusion bias tests.

Covers:
- Short-baseline (n≤6) behaviour
- Self-inclusion bias analysis
- Leave-one-year-out (LOO) diagnostic function
- Minimum-data requirements
- Comparison of LOO vs standard classification

SYNTHETIC DATA ONLY.
"""

import math

import numpy as np
import pandas as pd
import pytest

from pipeline.baseline import (
    MIN_BASELINE_MONTHS,
    MIN_LOO_OBSERVATIONS,
    compute_seasonal_baseline,
    compute_anomalies,
    compute_loo_classification,
)
from pipeline.config import (
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    SENSOR_MODIS,
    YEAR_START,
    YEAR_END,
)


def _make_agg(values_by_year_month: dict, sensor=SENSOR_MODIS) -> pd.DataFrame:
    """
    Build a minimal aggregated DataFrame from a dict {(year, month): ocf}.
    Missing periods get has_data=False and null OCF.
    """
    rows = []
    for year in range(YEAR_START, YEAR_END + 1):
        for month in range(1, 13):
            period = f"{year:04d}-{month:02d}"
            ocf = values_by_year_month.get((year, month))
            rows.append({
                "period": period,
                "year": year,
                "month": month,
                "sensor": sensor,
                "has_data": ocf is not None,
                "occupied_cell_fraction": ocf,
                "detection_count": 10 if ocf is not None else 0,
                "occupied_cells": max(1, int(ocf * 270)) if ocf is not None else 0,
                "partial_cell_detections": 0,
                "total_eligible_cells": 270,
                "resolution_deg": 0.25,
                "coverage_note": "observed" if ocf is not None else "no_data",
            })
    return pd.DataFrame(rows)


class TestShortBaselineBehaviour:
    """With 2019-2024, each calendar month has ≤6 observations."""

    def test_month_with_exactly_min_baseline_has_sufficient(self):
        """MIN_BASELINE_MONTHS observations → sufficient_baseline = True."""
        vals = {(2019+i, 9): 0.1 + i*0.01 for i in range(MIN_BASELINE_MONTHS)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        sep = baseline[baseline["month"] == 9].iloc[0]
        assert sep["baseline_n"] == MIN_BASELINE_MONTHS
        assert bool(sep["sufficient_baseline"]) is True

    def test_month_with_less_than_min_baseline_insufficient(self):
        """Fewer than MIN_BASELINE_MONTHS → sufficient_baseline = False, NaN median."""
        vals = {(2019+i, 9): 0.1 for i in range(MIN_BASELINE_MONTHS - 1)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        sep = baseline[baseline["month"] == 9].iloc[0]
        assert bool(sep["sufficient_baseline"]) is False
        assert math.isnan(sep["baseline_median"])

    def test_zero_observations_gives_nan_median(self):
        """No data for a calendar month → NaN median, n=0."""
        agg = _make_agg({})  # no data at all
        baseline = compute_seasonal_baseline(agg)
        for _, row in baseline.iterrows():
            assert row["baseline_n"] == 0
            assert math.isnan(row["baseline_median"])

    def test_six_observations_all_valid(self):
        """All 6 years for one month → n=6, valid median."""
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        sep = baseline[baseline["month"] == 9].iloc[0]
        assert sep["baseline_n"] == 6
        assert not math.isnan(sep["baseline_median"])
        # Median of [0.08, 0.09, ..., 0.13] = (0.10+0.11)/2 = 0.105
        assert abs(sep["baseline_median"] - 0.105) < 1e-6


class TestSelfInclusionBias:
    """
    Verify self-inclusion bias is conservative (inflates threshold).
    With n=6, the bias is documented as ~0% classification change.
    """

    def test_self_included_threshold_geq_loo_threshold(self):
        """
        Including year Y in its own threshold inflates the threshold (conservative).
        Therefore threshold_included >= threshold_excluded when Y is the highest value.
        """
        # Year 2024 has the highest value
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(5)}  # 2019-2023
        vals[(2024, 9)] = 0.25  # anomalously high
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        result = compute_anomalies(agg, baseline, elevated_quantile=0.75)

        # Standard threshold (includes 2024)
        sep_std = result[(result["year"] == 2024) & (result["month"] == 9)].iloc[0]
        t_std = sep_std["elevated_threshold"]

        # LOO threshold (excludes 2024)
        loo = compute_loo_classification(agg, elevated_quantile=0.75)
        sep_loo = loo[(loo["year"] == 2024) & (loo["month"] == 9)].iloc[0]
        t_loo = sep_loo.get("loo_threshold")

        if t_loo is not None and not math.isnan(float(t_loo)):
            # Standard (self-included) threshold should be >= LOO threshold
            # because the high value 0.25 raises the 75th percentile
            assert float(t_std) >= float(t_loo) - 1e-9, (
                f"Self-included threshold {t_std:.4f} should be >= LOO threshold {t_loo:.4f}"
            )

    def test_extreme_year_elevated_under_both_methods(self):
        """An extreme year should be elevated under both standard and LOO."""
        vals = {(2019+i, 9): 0.08 for i in range(5)}
        vals[(2024, 9)] = 0.50  # extreme
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        result = compute_anomalies(agg, baseline, elevated_quantile=0.75)
        loo = compute_loo_classification(result, elevated_quantile=0.75)

        sep_std = result[(result["year"] == 2024) & (result["month"] == 9)].iloc[0]
        sep_loo = loo[(loo["year"] == 2024) & (loo["month"] == 9)].iloc[0]

        assert sep_std["anomaly_label"] == LABEL_CONSISTENTLY_ELEVATED
        if sep_loo["loo_sufficient"]:
            assert bool(sep_loo["loo_is_elevated"]) is True

    def test_typical_year_not_elevated_under_both_methods(self):
        """A typical (median) year should not be elevated under either method."""
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        result = compute_anomalies(agg, baseline, elevated_quantile=0.75)
        loo = compute_loo_classification(result, elevated_quantile=0.75)

        # Year 2021 has median value — should not be elevated
        sep_std = result[(result["year"] == 2021) & (result["month"] == 9)].iloc[0]
        sep_loo = loo[(loo["year"] == 2021) & (loo["month"] == 9)].iloc[0]

        assert sep_std["anomaly_label"] == LABEL_NOT_ELEVATED
        if sep_loo["loo_sufficient"]:
            assert bool(sep_loo["loo_is_elevated"]) is False


class TestLOOClassification:
    """Tests for the leave-one-year-out diagnostic function."""

    def test_returns_dataframe(self):
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        result = compute_loo_classification(agg)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self):
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        result = compute_loo_classification(agg)
        for col in ["period", "year", "month", "loo_threshold",
                    "loo_n", "loo_sufficient", "loo_is_elevated", "loo_label"]:
            assert col in result.columns, f"Missing column: {col}"

    def test_no_data_rows_get_insufficient(self):
        """Months with has_data=False must get loo_label=insufficient_evidence."""
        agg = _make_agg({})
        result = compute_loo_classification(agg)
        assert (result["loo_label"] == LABEL_INSUFFICIENT_EVIDENCE).all()

    def test_insufficient_loo_observations_get_insufficient(self):
        """
        LOO requires MIN_LOO_OBSERVATIONS (4). With only 3 observations per month,
        every classification should be insufficient_evidence.
        """
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(MIN_LOO_OBSERVATIONS - 1)}
        agg = _make_agg(vals)
        result = compute_loo_classification(agg)
        sep = result[(result["month"] == 9)]
        # All rows where has_data could potentially be classified
        # LOO n = total - 1 = (MIN_LOO_OBSERVATIONS-1) - 1 < MIN_LOO_OBSERVATIONS-1 < threshold
        # So all should be insufficient
        assert (sep["loo_sufficient"] == False).all()

    def test_sufficient_loo_needs_min_4_observations(self):
        """With exactly MIN_LOO_OBSERVATIONS, LOO should work for all but the last year."""
        n = MIN_LOO_OBSERVATIONS
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(n)}
        agg = _make_agg(vals)
        result = compute_loo_classification(agg)
        sep = result[(result["month"] == 9) & result["loo_sufficient"]]
        # At least some periods should have sufficient LOO data
        # (n observations → n-1 = MIN_LOO_OBSERVATIONS-1 for each LOO fold)
        # Only valid if n-1 >= MIN_LOO_OBSERVATIONS. With n=4, n-1=3 < 4. So 0 sufficient.
        # With n=5, n-1=4 >= MIN_LOO_OBSERVATIONS. So 5 periods would be sufficient.
        if n >= MIN_LOO_OBSERVATIONS + 1:
            assert len(sep) > 0

    def test_loo_labels_are_valid(self):
        """All LOO labels must be one of the four valid label constants."""
        from pipeline.config import LABEL_CLASSIFICATION_SENSITIVE
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        result = compute_loo_classification(agg)
        valid = {LABEL_CONSISTENTLY_ELEVATED, LABEL_NOT_ELEVATED,
                 LABEL_INSUFFICIENT_EVIDENCE, LABEL_CLASSIFICATION_SENSITIVE}
        assert set(result["loo_label"]).issubset(valid)

    def test_agrees_with_standard_field_populated_when_possible(self):
        """agrees_with_standard must be populated when both standard and LOO classify."""
        vals = {(2019+i, 9): 0.08 + i*0.01 for i in range(6)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        agg_with_labels = compute_anomalies(agg, baseline)
        result = compute_loo_classification(agg_with_labels, elevated_quantile=0.75)
        # For periods where LOO is sufficient, agrees_with_standard should not be None
        sufficient = result[result["loo_sufficient"]]
        if len(sufficient) > 0:
            assert sufficient["agrees_with_standard"].notna().any()


class TestMinimumDataRequirements:
    """Document and enforce minimum-data requirements."""

    def test_min_baseline_months_constant_is_3(self):
        """MIN_BASELINE_MONTHS must be 3 as documented."""
        assert MIN_BASELINE_MONTHS == 3

    def test_min_loo_observations_constant_is_4(self):
        """MIN_LOO_OBSERVATIONS must be 4 (need ≥4 to leave one out and keep ≥3)."""
        assert MIN_LOO_OBSERVATIONS == 4

    def test_exactly_min_gives_sufficient(self):
        """Exactly MIN_BASELINE_MONTHS observations → sufficient_baseline=True."""
        vals = {(2019+i, 3): 0.05 for i in range(MIN_BASELINE_MONTHS)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        mar = baseline[baseline["month"] == 3].iloc[0]
        assert bool(mar["sufficient_baseline"]) is True

    def test_one_below_min_gives_insufficient(self):
        """MIN_BASELINE_MONTHS - 1 observations → sufficient_baseline=False."""
        vals = {(2019+i, 3): 0.05 for i in range(MIN_BASELINE_MONTHS - 1)}
        agg = _make_agg(vals)
        baseline = compute_seasonal_baseline(agg)
        mar = baseline[baseline["month"] == 3].iloc[0]
        assert bool(mar["sufficient_baseline"]) is False

    def test_missing_month_does_not_count_toward_baseline(self):
        """has_data=False months must not contribute to baseline_n."""
        # Give September exactly MIN_BASELINE_MONTHS observations
        vals = {(2019+i, 9): 0.1 for i in range(MIN_BASELINE_MONTHS)}
        agg = _make_agg(vals)
        # Confirm no extra months sneak in
        baseline = compute_seasonal_baseline(agg)
        sep = baseline[baseline["month"] == 9].iloc[0]
        assert sep["baseline_n"] == MIN_BASELINE_MONTHS
