"""Regression tests for source-aware NASA FIRMS ingestion."""

import hashlib
import json

import pandas as pd
import pytest

import pipeline.ingest as ingest
from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS
from pipeline.normalize import normalize
from pipeline.validate import validate_raw


def _source_row(sensor, source_type, date, confidence="n", satellite=None):
    is_modis = sensor == SENSOR_MODIS
    version = (
        "6.03" if is_modis else "2"
    ) if source_type == "archive" else (
        "6.1NRT" if is_modis else "2.0NRT"
    )
    row = {
        "latitude": "-2.5",
        "longitude": "103.5",
        "brightness": "330.0",
        "scan": "0.5",
        "track": "0.5",
        "acq_date": date,
        "acq_time": "0630",
        "satellite": satellite or ("Terra" if is_modis else "N20"),
        "instrument": "MODIS" if is_modis else "VIIRS",
        "confidence": "85" if is_modis else confidence,
        "version": version,
        "bright_t31": "290.0",
        "frp": "12.5",
        "daynight": "D",
    }
    if source_type == "archive":
        row["type"] = "0"
    return row


def _write_firms_file(sensor_dir, sensor, source_type, date, **row_overrides):
    product_code = "M-C61" if sensor == SENSOR_MODIS else "J1V-C2"
    filename = f"fire_{source_type}_{product_code}_849850.csv"
    if sensor == SENSOR_VIIRS:
        filename = f"fire_{source_type}_{product_code}_849851.csv"
    path = sensor_dir / source_type / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    row = _source_row(sensor, source_type, date, **row_overrides)
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


@pytest.mark.parametrize("sensor", [SENSOR_MODIS, SENSOR_VIIRS])
def test_ingests_nested_archive_and_nrt_with_manifest_provenance(
    tmp_path, monkeypatch, sensor
):
    sensor_dir = tmp_path / sensor
    archive_path = _write_firms_file(
        sensor_dir, sensor, "archive", "2024-06-01", confidence="n"
    )
    nrt_path = _write_firms_file(
        sensor_dir, sensor, "nrt", "2024-07-01", confidence="l"
    )
    manifest_dir = tmp_path / "manifests"
    monkeypatch.setitem(ingest.SENSOR_DIRS, sensor, sensor_dir)
    monkeypatch.setattr(ingest, "DATA_MANIFESTS", manifest_dir)

    raw, manifest = ingest.ingest_sensor(sensor)

    assert raw is not None
    assert len(raw) == 2
    assert set(raw["_source_type"]) == {"archive", "nrt"}
    assert set(raw["_request_id"]) == {"849850" if sensor == SENSOR_MODIS else "849851"}
    assert set(raw["_product_code"]) == {"M-C61" if sensor == SENSOR_MODIS else "J1V-C2"}

    by_name = {entry["filename"]: entry for entry in manifest["files"]}
    for path in (archive_path, nrt_path):
        entry = by_name[path.name]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["request_id"] == ("849850" if sensor == SENSOR_MODIS else "849851")
        assert not entry["validation_errors"]
        assert entry["validation_metrics"]["malformed_coordinates"] == 0
        assert entry["validation_metrics"]["malformed_timestamps"] == 0
        assert entry["validation_metrics"]["out_of_bbox"] == 0

    saved_manifest = json.loads(
        (manifest_dir / f"{sensor}_manifest.json").read_text(encoding="utf-8")
    )
    assert saved_manifest["manifest_version"] == 2
    assert {entry["source_type"] for entry in saved_manifest["files"]} == {"archive", "nrt"}


def test_viirs_real_firms_schema_uses_no_unverified_thermal_alias(tmp_path, monkeypatch):
    sensor_dir = tmp_path / SENSOR_VIIRS
    _write_firms_file(sensor_dir, SENSOR_VIIRS, "archive", "2024-06-01")
    _write_firms_file(
        sensor_dir, SENSOR_VIIRS, "nrt", "2024-07-01", confidence="l"
    )
    monkeypatch.setitem(ingest.SENSOR_DIRS, SENSOR_VIIRS, sensor_dir)
    monkeypatch.setattr(ingest, "DATA_MANIFESTS", tmp_path / "manifests")

    raw, manifest = ingest.ingest_sensor(SENSOR_VIIRS)
    assert raw is not None
    assert "brightness" in raw.columns and "bright_t31" in raw.columns
    assert "bright_ti4" not in raw.columns and "bright_ti5" not in raw.columns

    normalized, stats = normalize(raw, SENSOR_VIIRS)

    assert stats.rows_in == 2
    assert stats.excluded_low_confidence == 1
    assert stats.rows_out == 1
    assert "brightness" not in normalized.columns
    assert "bright_t31" not in normalized.columns
    assert "bright_ti4" not in normalized.columns
    assert "bright_ti5" not in normalized.columns
    # Archive-only `type` is optional: present in the raw archive rows, never required or output.
    assert "type" in raw.columns
    assert "type" not in normalized.columns
    assert normalized.loc[0, "_source_type"] == "archive"
    assert normalized.loc[0, "_request_id"] == "849851"
    assert manifest["files"]


def test_archive_nrt_date_overlap_blocks_sensor_ingestion(tmp_path, monkeypatch):
    sensor_dir = tmp_path / SENSOR_VIIRS
    _write_firms_file(sensor_dir, SENSOR_VIIRS, "archive", "2024-06-01")
    _write_firms_file(sensor_dir, SENSOR_VIIRS, "nrt", "2024-06-01")
    monkeypatch.setitem(ingest.SENSOR_DIRS, SENSOR_VIIRS, sensor_dir)
    monkeypatch.setattr(ingest, "DATA_MANIFESTS", tmp_path / "manifests")

    raw, manifest = ingest.ingest_sensor(SENSOR_VIIRS)

    assert raw is None
    assert manifest["overlapping_archive_nrt_dates"] == ["2024-06-01"]
    assert "blocking_errors" in manifest
    assert all(entry["validation_errors"] for entry in manifest["files"])


def test_wrong_viirs_platform_is_rejected(tmp_path, monkeypatch):
    sensor_dir = tmp_path / SENSOR_VIIRS
    _write_firms_file(
        sensor_dir, SENSOR_VIIRS, "archive", "2024-06-01", satellite="N21"
    )
    monkeypatch.setitem(ingest.SENSOR_DIRS, SENSOR_VIIRS, sensor_dir)
    monkeypatch.setattr(ingest, "DATA_MANIFESTS", tmp_path / "manifests")

    raw, manifest = ingest.ingest_sensor(SENSOR_VIIRS)

    assert raw is None
    assert any("satellite identifiers" in error for error in manifest["files"][0]["validation_errors"])


def test_nrt_source_rejects_archive_version(tmp_path, monkeypatch):
    sensor_dir = tmp_path / SENSOR_MODIS
    path = _write_firms_file(sensor_dir, SENSOR_MODIS, "nrt", "2024-06-01")
    df = ingest._load_csv(path)
    df["version"] = "6.03"

    result = validate_raw(df, SENSOR_MODIS, source_type="nrt")

    assert not result.is_valid
    assert any("NRT suffix" in error for error in result.errors)
