"""
Unit tests for pipeline.baseline

SYNTHETIC FIXTURE DATA ONLY.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.config import (
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    SENSOR_MODIS,
)
from pipeline.aggregate import aggregate_monthly
from pipeline.baseline import compute_seasonal_baseline, compute_anomalies
from pipeline.normalize import normalize


@pytest.fixture
def agg_modis(modis_raw_df):
    df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
    return aggregate_monthly(df_clean, SENSOR_MODIS)


class TestSeasonalBaseline:
    def test_returns_12_months(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        assert len(baseline) == 12

    def test_months_one_to_twelve(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        assert set(baseline["month"]) == set(range(1, 13))

    def test_insufficient_data_gives_nan(self, agg_modis):
        """Months with fewer than MIN_BASELINE_MONTHS should have NaN median."""
        from pipeline.baseline import MIN_BASELINE_MONTHS
        baseline = compute_seasonal_baseline(agg_modis)
        # For months where n < MIN_BASELINE_MONTHS, median must be NaN
        low_n = baseline[~baseline["sufficient_baseline"]]
        assert low_n["baseline_median"].isna().all()

    def test_baseline_median_non_negative(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        valid = baseline["baseline_median"].dropna()
        assert (valid >= 0).all()


class TestAnomalyClassification:
    def test_anomaly_df_has_required_columns(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        result = compute_anomalies(agg_modis, baseline)
        for col in ["anomaly_label", "is_elevated", "anomaly"]:
            assert col in result.columns, f"Missing: {col}"

    def test_no_data_rows_get_insufficient_evidence(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        result = compute_anomalies(agg_modis, baseline)
        no_data = result[~result["has_data"]]
        assert (no_data["anomaly_label"] == LABEL_INSUFFICIENT_EVIDENCE).all()

    def test_elevated_label_requires_has_data(self, agg_modis):
        baseline = compute_seasonal_baseline(agg_modis)
        result = compute_anomalies(agg_modis, baseline)
        elevated = result[result["anomaly_label"] == LABEL_CONSISTENTLY_ELEVATED]
        assert elevated["has_data"].all()

    def test_all_labels_valid(self, agg_modis):
        from pipeline.config import LABEL_CLASSIFICATION_SENSITIVE
        baseline = compute_seasonal_baseline(agg_modis)
        result = compute_anomalies(agg_modis, baseline)
        valid_labels = {
            LABEL_CONSISTENTLY_ELEVATED,
            LABEL_NOT_ELEVATED,
            LABEL_INSUFFICIENT_EVIDENCE,
            LABEL_CLASSIFICATION_SENSITIVE,
        }
        assert set(result["anomaly_label"]).issubset(valid_labels)
