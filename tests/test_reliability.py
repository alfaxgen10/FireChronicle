"""
Unit tests for pipeline.reliability

Three canonical scenarios from Blueprint §08:
  1. All configurations agree: elevated
  2. Configurations disagree: sensitive
  3. Insufficient coverage
"""

import pandas as pd
import pytest

from pipeline.config import (
    LABEL_CLASSIFICATION_SENSITIVE,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
    SENSOR_MODIS,
    SENSOR_VIIRS,
)
from pipeline.reliability import compute_stability_summary


def _make_reliability_row(period, sensor, config_name, label):
    return {
        "period":                  period,
        "year":                    int(period[:4]),
        "month":                   int(period[5:7]),
        "config_name":             config_name,
        "sensor":                  sensor,
        "resolution_deg":          0.25,
        "occupied_cell_fraction":  0.3,
        "is_elevated":             label == LABEL_CONSISTENTLY_ELEVATED,
        "anomaly_label":           label,
        "anomaly_note":            "fixture",
        "is_fixture":              True,
        "baseline_median":         0.2,
        "baseline_n":              5,
        "sufficient_baseline":     True,
    }


class TestStabilityLabels:
    def test_all_elevated_gives_consistently_elevated(self):
        """Blueprint: 'Consistently elevated' when all configs agree elevated."""
        rows = [
            _make_reliability_row("2021-09", SENSOR_MODIS, "cfg_a", LABEL_CONSISTENTLY_ELEVATED),
            _make_reliability_row("2021-09", SENSOR_VIIRS, "cfg_b", LABEL_CONSISTENTLY_ELEVATED),
        ]
        df = pd.DataFrame(rows)
        summary = compute_stability_summary(df)
        row = summary[summary["period"] == "2021-09"].iloc[0]
        assert row["stability_label"] == LABEL_CONSISTENTLY_ELEVATED

    def test_disagreement_gives_sensitive(self):
        """Blueprint: 'Classification-sensitive' when configs disagree."""
        rows = [
            _make_reliability_row("2021-10", SENSOR_MODIS, "cfg_a", LABEL_CONSISTENTLY_ELEVATED),
            _make_reliability_row("2021-10", SENSOR_VIIRS, "cfg_b", LABEL_NOT_ELEVATED),
        ]
        df = pd.DataFrame(rows)
        summary = compute_stability_summary(df)
        row = summary[summary["period"] == "2021-10"].iloc[0]
        assert row["stability_label"] == LABEL_CLASSIFICATION_SENSITIVE

    def test_insufficient_coverage_gives_insufficient(self):
        """Blueprint: 'Insufficient evidence' when coverage fails."""
        rows = [
            _make_reliability_row("2021-11", SENSOR_MODIS, "cfg_a", LABEL_INSUFFICIENT_EVIDENCE),
            _make_reliability_row("2021-11", SENSOR_VIIRS, "cfg_b", LABEL_INSUFFICIENT_EVIDENCE),
        ]
        df = pd.DataFrame(rows)
        summary = compute_stability_summary(df)
        row = summary[summary["period"] == "2021-11"].iloc[0]
        assert row["stability_label"] == LABEL_INSUFFICIENT_EVIDENCE

    def test_all_not_elevated_gives_not_elevated(self):
        rows = [
            _make_reliability_row("2021-12", SENSOR_MODIS, "cfg_a", LABEL_NOT_ELEVATED),
            _make_reliability_row("2021-12", SENSOR_VIIRS, "cfg_b", LABEL_NOT_ELEVATED),
        ]
        df = pd.DataFrame(rows)
        summary = compute_stability_summary(df)
        row = summary[summary["period"] == "2021-12"].iloc[0]
        assert row["stability_label"] == LABEL_NOT_ELEVATED

    def test_empty_df_returns_empty(self):
        df = pd.DataFrame()
        summary = compute_stability_summary(df)
        assert summary.empty
