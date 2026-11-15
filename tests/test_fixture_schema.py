"""The synthetic fixtures must match the input schema the pipeline supports.

VIIRS headers below were verified directly against the NASA FIRMS source files
used for the released outputs (request 849851): fire_archive_J1V-C2_849851.csv
and fire_nrt_J1V-C2_849851.csv. Only these two headers and their confidence
representation were verified; other or future FIRMS export variants were not.
"""

from pathlib import Path

from pipeline.config import (
    MODIS_REQUIRED_COLUMNS,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    VIIRS_CONFIDENCE_KEEP,
    VIIRS_REQUIRED_COLUMNS,
)
from pipeline.normalize import normalize
from pipeline.validate import validate_raw
from tests.test_ingest import _source_row

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures"

VERIFIED_VIIRS_ARCHIVE_HEADER = [
    "latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version", "bright_t31", "frp",
    "daynight", "type",
]
VERIFIED_VIIRS_NRT_HEADER = VERIFIED_VIIRS_ARCHIVE_HEADER[:-1]
VERIFIED_VIIRS_CONFIDENCE_VALUES = {"h", "l", "n"}  # only values present in either file


def test_verified_headers_satisfy_pipeline_requirements():
    for header in (VERIFIED_VIIRS_ARCHIVE_HEADER, VERIFIED_VIIRS_NRT_HEADER):
        assert VIIRS_REQUIRED_COLUMNS <= set(header)
    # `type` exists only in the archive export, so it must not be required.
    assert "type" not in VIIRS_REQUIRED_COLUMNS
    assert "type" not in VERIFIED_VIIRS_NRT_HEADER


def test_viirs_fixture_header_matches_verified_nrt_header():
    header = (FIXTURES / "viirs_sample.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == VERIFIED_VIIRS_NRT_HEADER


def test_ingest_test_rows_match_verified_headers():
    """The synthetic rows used by the real-schema ingestion tests use the verified headers."""
    assert list(_source_row(SENSOR_VIIRS, "archive", "2024-06-01")) == VERIFIED_VIIRS_ARCHIVE_HEADER
    assert list(_source_row(SENSOR_VIIRS, "nrt", "2024-06-01")) == VERIFIED_VIIRS_NRT_HEADER


def test_viirs_fixture_uses_no_unverified_thermal_names(viirs_raw_df):
    # The source names its thermal fields brightness / bright_t31. Their mapping
    # to VIIRS I4/I5 is unverified, so no I4/I5 names are used or inferred.
    assert not {"bright_ti4", "bright_ti5"} & set(viirs_raw_df.columns)


def test_viirs_fixture_platform_matches_source_metadata(viirs_raw_df):
    # Real VIIRS manifests record satellite "N20" and instrument "VIIRS".
    assert set(viirs_raw_df["satellite"]) == {"N20"}
    assert set(viirs_raw_df["instrument"]) == {"VIIRS"}
    assert set(viirs_raw_df["version"]) == {"2.0NRT"}


def test_viirs_fixture_confidence_uses_verified_representation(viirs_raw_df):
    assert set(viirs_raw_df["confidence"]) == VERIFIED_VIIRS_CONFIDENCE_VALUES
    # Policy: n and h retained, l excluded.
    assert {"n", "h"} <= VIIRS_CONFIDENCE_KEEP
    assert "l" not in VIIRS_CONFIDENCE_KEEP


def test_viirs_fixture_validates_as_nrt_source(viirs_raw_df):
    result = validate_raw(viirs_raw_df, SENSOR_VIIRS, "viirs_sample.csv", source_type="nrt")
    assert result.is_valid, result.errors


def test_viirs_fixture_scenarios_preserved(viirs_raw_df):
    result = validate_raw(viirs_raw_df, SENSOR_VIIRS, "viirs_sample.csv")
    assert result.total_rows == 10
    assert result.low_confidence_rows == 1   # the single "l" row
    assert result.out_of_bbox == 1
    assert result.duplicate_rows == 1

    _, stats = normalize(viirs_raw_df, SENSOR_VIIRS)
    assert stats.rows_in == 10
    assert stats.excluded_low_confidence == 1
    assert stats.excluded_duplicates == 1
    assert stats.rows_out == 8


def test_modis_fixture_has_required_columns(modis_raw_df):
    assert MODIS_REQUIRED_COLUMNS <= set(modis_raw_df.columns)
    assert validate_raw(modis_raw_df, SENSOR_MODIS, "modis_sample.csv").is_valid
