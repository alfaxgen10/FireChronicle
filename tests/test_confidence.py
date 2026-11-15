"""
Tests for MODIS integer confidence filtering and VIIRS string confidence.

These tests document the critical real-data behaviour: MODIS CSVs from
NASA FIRMS use INTEGER confidence values 0–100, not string labels.

SYNTHETIC FIXTURE DATA ONLY.
"""

import pandas as pd
import pytest

from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS, MODIS_CONFIDENCE_MIN_INT
from pipeline.normalize import normalize


def _make_modis_row(**kwargs):
    """Return one MODIS-format row dict with defaults."""
    base = dict(
        latitude=-2.5, longitude=103.5, brightness=320.0,
        scan=1.0, track=1.0,
        acq_date="2021-09-15", acq_time=630,
        satellite="Terra", version="6.1NRT",
        bright_t31=295.0, frp=22.0, daynight="D",
        _source_file="test", _sensor=SENSOR_MODIS,
    )
    base.update(kwargs)
    return base


def _make_viirs_row(**kwargs):
    """Return one VIIRS-format row dict with defaults."""
    base = dict(
        latitude=-2.5, longitude=103.5, brightness=330.0,
        scan=0.75, track=0.75,
        acq_date="2021-09-15", acq_time=630,
        satellite="N20", instrument="VIIRS", version="2.0NRT",
        bright_t31=300.0, frp=25.0, daynight="D",
        _source_file="test", _sensor=SENSOR_VIIRS,
    )
    base.update(kwargs)
    return base


class TestMODISIntegerConfidence:
    """MODIS confidence is integer 0-100 in real NASA FIRMS CSVs."""

    def test_high_confidence_integer_kept(self):
        df = pd.DataFrame([_make_modis_row(confidence=92)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.rows_out == 1
        assert stats.excluded_low_confidence == 0

    def test_nominal_confidence_integer_kept(self):
        """confidence=50 should be kept (>= MODIS_CONFIDENCE_MIN_INT=30)."""
        df = pd.DataFrame([_make_modis_row(confidence=50)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.rows_out == 1
        assert stats.excluded_low_confidence == 0

    def test_low_confidence_integer_excluded(self):
        """confidence=15 is below 30 → excluded."""
        df = pd.DataFrame([_make_modis_row(confidence=15)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.excluded_low_confidence == 1
        assert stats.rows_out == 0

    def test_zero_confidence_excluded(self):
        df = pd.DataFrame([_make_modis_row(confidence=0)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.excluded_low_confidence == 1

    def test_boundary_value_at_min(self):
        """confidence == MODIS_CONFIDENCE_MIN_INT should be KEPT."""
        df = pd.DataFrame([_make_modis_row(confidence=MODIS_CONFIDENCE_MIN_INT)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.rows_out == 1, f"confidence={MODIS_CONFIDENCE_MIN_INT} should be kept"

    def test_boundary_value_just_below_min(self):
        """confidence == MODIS_CONFIDENCE_MIN_INT - 1 should be EXCLUDED."""
        df = pd.DataFrame([_make_modis_row(confidence=MODIS_CONFIDENCE_MIN_INT - 1)], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.excluded_low_confidence == 1

    def test_mixed_confidence_counts(self):
        """3 high + 2 low → 2 excluded."""
        rows = [
            _make_modis_row(confidence=85, acq_time=630),
            _make_modis_row(confidence=72, acq_time=631, latitude=-3.0),
            _make_modis_row(confidence=55, acq_time=632, latitude=-3.1),
            _make_modis_row(confidence=10, acq_time=633, latitude=-3.2),
            _make_modis_row(confidence=5,  acq_time=634, latitude=-3.3),
        ]
        df = pd.DataFrame(rows, dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.excluded_low_confidence == 2
        assert stats.rows_out == 3

    def test_string_confidence_fallback_nominal(self):
        """NRT files occasionally ship string labels; nominal/high must pass."""
        df = pd.DataFrame([_make_modis_row(confidence="nominal")], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.rows_out == 1

    def test_string_confidence_fallback_low_excluded(self):
        df = pd.DataFrame([_make_modis_row(confidence="low")], dtype=object)
        clean, stats = normalize(df, SENSOR_MODIS)
        assert stats.excluded_low_confidence == 1


class TestVIIRSStringConfidence:
    """VIIRS confidence is a string: low / nominal / high."""

    def test_nominal_string_kept(self):
        df = pd.DataFrame([_make_viirs_row(confidence="nominal")], dtype=object)
        clean, stats = normalize(df, SENSOR_VIIRS)
        assert stats.rows_out == 1

    def test_high_string_kept(self):
        df = pd.DataFrame([_make_viirs_row(confidence="high")], dtype=object)
        clean, stats = normalize(df, SENSOR_VIIRS)
        assert stats.rows_out == 1

    def test_low_string_excluded(self):
        df = pd.DataFrame([_make_viirs_row(confidence="low")], dtype=object)
        clean, stats = normalize(df, SENSOR_VIIRS)
        assert stats.excluded_low_confidence == 1

    def test_case_insensitive(self):
        """Confidence strings from FIRMS may be title-cased."""
        df = pd.DataFrame([_make_viirs_row(confidence="Nominal")], dtype=object)
        clean, stats = normalize(df, SENSOR_VIIRS)
        assert stats.rows_out == 1

    def test_single_letter_abbrev(self):
        """Some archive files use 'n'/'h'/'l'."""
        for abbrev, expected_kept in [("n", 1), ("h", 1), ("l", 0)]:
            df = pd.DataFrame([_make_viirs_row(confidence=abbrev)], dtype=object)
            clean, stats = normalize(df, SENSOR_VIIRS)
            assert stats.rows_out == expected_kept, f"abbrev={abbrev!r}"
