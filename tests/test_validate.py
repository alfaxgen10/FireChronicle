"""
Unit tests for pipeline.validate

All inputs are SYNTHETIC FIXTURES.  Real NASA data is never used in unit tests.
"""

import pandas as pd
import pytest

from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS
from pipeline.validate import validate_raw


class TestValidateMODIS:
    def test_valid_df_passes(self, modis_raw_df):
        result = validate_raw(modis_raw_df, SENSOR_MODIS, "modis_sample.csv")
        # Validation should not error (warnings are acceptable)
        assert result.is_valid, f"Expected valid; errors: {result.errors}"

    def test_total_rows_recorded(self, modis_raw_df):
        result = validate_raw(modis_raw_df, SENSOR_MODIS)
        assert result.total_rows == len(modis_raw_df)

    def test_low_confidence_flagged(self, modis_raw_df):
        result = validate_raw(modis_raw_df, SENSOR_MODIS)
        # Fixture has 2 low-confidence rows
        assert result.low_confidence_rows >= 2

    def test_out_of_bbox_flagged(self, modis_raw_df):
        result = validate_raw(modis_raw_df, SENSOR_MODIS)
        # Fixture has 1 row outside bbox
        assert result.out_of_bbox >= 1

    def test_duplicates_flagged(self, modis_raw_df):
        result = validate_raw(modis_raw_df, SENSOR_MODIS)
        # Fixture has 1 duplicate
        assert result.duplicate_rows >= 1

    def test_missing_column_causes_error(self, modis_raw_df):
        df_bad = modis_raw_df.drop(columns=["latitude"])
        result = validate_raw(df_bad, SENSOR_MODIS)
        assert not result.is_valid
        assert any("latitude" in e.lower() for e in result.errors)

    def test_all_outside_bbox_causes_error(self):
        df = pd.DataFrame({
            "latitude":    [50.0, 51.0],
            "longitude":   [10.0, 11.0],
            "brightness":  ["320", "321"],
            "scan":        ["1.0", "1.0"],
            "track":       ["1.0", "1.0"],
            "acq_date":    ["2021-09-15", "2021-09-16"],
            "acq_time":    ["630", "630"],
            "satellite":   ["Terra", "Terra"],
            "confidence":  ["nominal", "nominal"],
            "version":     ["6.1NRT", "6.1NRT"],
            "bright_t31":  ["295", "295"],
            "frp":         ["20", "20"],
            "daynight":    ["D", "D"],
        })
        result = validate_raw(df, SENSOR_MODIS)
        assert not result.is_valid


class TestValidateVIIRS:
    def test_valid_viirs_df_passes(self, viirs_raw_df):
        result = validate_raw(viirs_raw_df, SENSOR_VIIRS, "viirs_sample.csv")
        assert result.is_valid, f"Expected valid; errors: {result.errors}"

    def test_summary_contains_sensor(self, viirs_raw_df):
        result = validate_raw(viirs_raw_df, SENSOR_VIIRS)
        summary = result.summary()
        assert SENSOR_VIIRS in summary
