"""
Unit tests for pipeline.aggregate

SYNTHETIC FIXTURE DATA ONLY.
"""

import pandas as pd
import pytest
import numpy as np

from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS, YEAR_START, YEAR_END
from pipeline.normalize import normalize
from pipeline.aggregate import aggregate_monthly, build_complete_month_index


@pytest.fixture
def normalized_modis(modis_raw_df):
    df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
    return df_clean


@pytest.fixture
def normalized_viirs(viirs_raw_df):
    df_clean, _ = normalize(viirs_raw_df, SENSOR_VIIRS)
    return df_clean


class TestCompleteMonthIndex:
    def test_covers_full_range(self):
        idx = build_complete_month_index(2019, 2024)
        expected_rows = (2024 - 2019 + 1) * 12
        assert len(idx) == expected_rows

    def test_all_months_present(self):
        idx = build_complete_month_index(2019, 2024)
        assert set(idx["month"]) == set(range(1, 13))

    def test_period_format(self):
        idx = build_complete_month_index(2019, 2019)
        assert idx["period"].iloc[0] == "2019-01"
        assert idx["period"].iloc[-1] == "2019-12"


class TestAggregateMonthly:
    def test_returns_expected_rows(self, normalized_modis):
        agg = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        expected = (YEAR_END - YEAR_START + 1) * 12
        assert len(agg) == expected

    def test_sensor_column_set(self, normalized_modis):
        agg = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        assert (agg["sensor"] == SENSOR_MODIS).all()

    def test_occupied_cell_fraction_in_range(self, normalized_modis):
        agg = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        valid = agg["occupied_cell_fraction"].dropna()
        assert (valid >= 0).all()
        assert (valid <= 1).all()

    def test_missing_months_are_null_not_zero(self, normalized_modis):
        """Months with no detections must have null OCF, not 0.0."""
        agg = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        no_data_rows = agg[~agg["has_data"]]
        assert no_data_rows["occupied_cell_fraction"].isna().all(), (
            "Months with no detections should have null occupied_cell_fraction, not 0.0"
        )

    def test_has_data_flag_consistent(self, normalized_modis):
        agg = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        # has_data=True implies detection_count > 0
        data_rows = agg[agg["has_data"]]
        assert (data_rows["detection_count"] > 0).all()

    def test_empty_df_returns_full_skeleton(self):
        """Empty input should return a full skeleton with all null OCF."""
        empty = pd.DataFrame()
        agg = aggregate_monthly(empty, SENSOR_MODIS)
        expected = (YEAR_END - YEAR_START + 1) * 12
        assert len(agg) == expected
        assert agg["has_data"].sum() == 0

    def test_sensors_not_merged(self, normalized_modis, normalized_viirs):
        """MODIS and VIIRS aggregates must remain separate DataFrames."""
        agg_m = aggregate_monthly(normalized_modis, SENSOR_MODIS)
        agg_v = aggregate_monthly(normalized_viirs, SENSOR_VIIRS)
        assert (agg_m["sensor"] == SENSOR_MODIS).all()
        assert (agg_v["sensor"] == SENSOR_VIIRS).all()
