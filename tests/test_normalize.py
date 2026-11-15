"""
Unit tests for pipeline.normalize

All inputs are SYNTHETIC FIXTURES.
"""

import pandas as pd
import pytest

from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS
from pipeline.normalize import normalize


class TestNormalizeMODIS:
    def test_returns_dataframe_and_stats(self, modis_raw_df):
        df_clean, stats = normalize(modis_raw_df, SENSOR_MODIS)
        assert isinstance(df_clean, pd.DataFrame)
        assert stats.rows_in == len(modis_raw_df)

    def test_low_confidence_excluded(self, modis_raw_df):
        df_clean, stats = normalize(modis_raw_df, SENSOR_MODIS)
        assert stats.excluded_low_confidence >= 2

    def test_duplicate_excluded(self, modis_raw_df):
        df_clean, stats = normalize(modis_raw_df, SENSOR_MODIS)
        assert stats.excluded_duplicates >= 1

    def test_outside_year_excluded(self, modis_raw_df):
        df_clean, stats = normalize(modis_raw_df, SENSOR_MODIS)
        # Fixture has one row from 2018
        assert stats.excluded_outside_years >= 1

    def test_output_has_required_columns(self, modis_raw_df):
        df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
        for col in ["latitude", "longitude", "acq_datetime_utc", "year", "month", "sensor"]:
            assert col in df_clean.columns, f"Missing column: {col}"

    def test_latitude_is_float(self, modis_raw_df):
        df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
        assert df_clean["latitude"].dtype == float

    def test_sensor_tag_correct(self, modis_raw_df):
        df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
        assert (df_clean["sensor"] == SENSOR_MODIS).all()

    def test_no_rows_outside_configured_years(self, modis_raw_df):
        from pipeline.config import YEAR_START, YEAR_END
        df_clean, _ = normalize(modis_raw_df, SENSOR_MODIS)
        assert df_clean["year"].between(YEAR_START, YEAR_END).all()


class TestNormalizeVIIRS:
    def test_viirs_normalizes_successfully(self, viirs_raw_df):
        df_clean, stats = normalize(viirs_raw_df, SENSOR_VIIRS)
        assert stats.rows_out > 0
        assert stats.rows_out < stats.rows_in  # some should be excluded

    def test_viirs_sensor_tag(self, viirs_raw_df):
        df_clean, _ = normalize(viirs_raw_df, SENSOR_VIIRS)
        assert (df_clean["sensor"] == SENSOR_VIIRS).all()
