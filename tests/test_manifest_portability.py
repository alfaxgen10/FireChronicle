"""Regression tests: source manifests must use portable, repository-relative paths."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pandas as pd
import pytest

import pipeline.ingest as ingest
from pipeline.config import PROJECT_ROOT, SENSOR_MODIS, SENSOR_VIIRS

ABSOLUTE_PATH = re.compile(r"(^[A-Za-z]:[\\/])|(^[\\/])|(\\\\)")
USER_DIR = re.compile(r"(?i)[\\/](users|home)[\\/]")


def _write_source(sensor_dir: Path, sensor: str, source_type: str, date: str) -> Path:
    is_modis = sensor == SENSOR_MODIS
    product, request = ("M-C61", "849850") if is_modis else ("J1V-C2", "849851")
    path = sensor_dir / source_type / f"fire_{source_type}_{product}_{request}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    version = ("6.03" if is_modis else "2") if source_type == "archive" else (
        "6.1NRT" if is_modis else "2.0NRT"
    )
    row = {
        "latitude": "-2.5", "longitude": "103.5", "brightness": "330.0",
        "scan": "0.5", "track": "0.5", "acq_date": date, "acq_time": "0630",
        "satellite": "Terra" if is_modis else "N20",
        "instrument": "MODIS" if is_modis else "VIIRS",
        "confidence": "85" if is_modis else "n", "version": version,
        "bright_t31": "290.0", "frp": "12.5", "daynight": "D",
    }
    if source_type == "archive":
        row["type"] = "0"
    pd.DataFrame([row]).to_csv(path, index=False)
    return path


def _ingest_into(root: Path, sensor: str, monkeypatch):
    """Run ingestion for a sensor whose repository lives at ``root``."""
    subdir = "modis" if sensor == SENSOR_MODIS else "viirs"
    sensor_dir = root / "data" / "raw" / subdir
    manifest_dir = root / "data" / "manifests"
    monkeypatch.setitem(ingest.SENSOR_DIRS, sensor, sensor_dir)
    monkeypatch.setattr(ingest, "DATA_MANIFESTS", manifest_dir)
    raw, manifest = ingest.ingest_sensor(sensor)
    saved = json.loads((manifest_dir / f"{sensor}_manifest.json").read_text(encoding="utf-8"))
    return raw, manifest, saved


def _assert_portable(value: str, root: Path) -> None:
    assert not ABSOLUTE_PATH.search(value), value
    assert not USER_DIR.search(value), value
    assert str(root) not in value
    assert "\\" not in value
    assert ".." not in value.split("/")


@pytest.mark.parametrize("sensor", [SENSOR_MODIS, SENSOR_VIIRS])
def test_generated_manifest_paths_are_repository_relative(tmp_path, monkeypatch, sensor):
    root = tmp_path / "Users" / "someone" / "clone-a"
    subdir = "modis" if sensor == SENSOR_MODIS else "viirs"
    sensor_dir = root / "data" / "raw" / subdir
    _write_source(sensor_dir, sensor, "archive", "2024-06-01")
    _write_source(sensor_dir, sensor, "nrt", "2024-07-01")

    raw, manifest, saved = _ingest_into(root, sensor, monkeypatch)

    assert raw is not None
    for entry in saved["files"]:
        _assert_portable(entry["path"], root)
        assert entry["path"].startswith(f"data/raw/{subdir}/")
        assert entry["path"].endswith("/" + entry["filename"])
    # The whole serialized manifest, not just "path", must be free of the root.
    text = json.dumps(saved)
    assert str(root) not in text and str(root).replace("\\", "\\\\") not in text
    # Lineage column carried into normalization uses the same convention.
    assert set(raw["_source_path"]) == {e["path"] for e in saved["files"]}


def test_manifest_loads_and_verifies_after_relocation(tmp_path, monkeypatch):
    """A manifest generated in one clone must resolve inside a moved clone."""
    original = tmp_path / "original-clone"
    sensor_dir = original / "data" / "raw" / "modis"
    _write_source(sensor_dir, SENSOR_MODIS, "archive", "2024-06-01")
    _write_source(sensor_dir, SENSOR_MODIS, "nrt", "2024-07-01")
    _, _, saved_original = _ingest_into(original, SENSOR_MODIS, monkeypatch)

    relocated = tmp_path / "elsewhere" / "relocated-clone"
    shutil.copytree(original, relocated)
    shutil.rmtree(original)

    saved = json.loads(
        (relocated / "data" / "manifests" / f"{SENSOR_MODIS}_manifest.json").read_text(encoding="utf-8")
    )
    assert saved == saved_original
    for entry in saved["files"]:
        resolved = ingest.resolve_manifest_path(entry["path"], project_root=relocated)
        assert resolved.is_file()
        assert hashlib.sha256(resolved.read_bytes()).hexdigest() == entry["sha256"]


def test_reingesting_relocated_clone_yields_identical_provenance(tmp_path, monkeypatch):
    """Paths, hashes, counts and identifiers do not depend on clone location."""
    first = tmp_path / "a"
    _write_source(first / "data" / "raw" / "viirs", SENSOR_VIIRS, "archive", "2024-06-01")
    _, _, saved_a = _ingest_into(first, SENSOR_VIIRS, monkeypatch)

    second = tmp_path / "deeper" / "b"
    shutil.copytree(first / "data" / "raw", second / "data" / "raw")
    _, _, saved_b = _ingest_into(second, SENSOR_VIIRS, monkeypatch)

    for key in ("generated_at",):
        saved_a.pop(key)
        saved_b.pop(key)
    assert saved_a == saved_b


@pytest.mark.parametrize("bad", [
    "C:\\Users\\someone\\data\\raw\\modis\\x.csv",
    "C:/Users/someone/x.csv",
    "/home/someone/x.csv",
    "\\\\server\\share\\x.csv",
    "data/raw/../../secret.csv",
])
def test_resolver_rejects_absolute_or_traversing_paths(bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=Path("/repo"))


@pytest.mark.parametrize("manifest_file", sorted((PROJECT_ROOT / "data" / "manifests").glob("*_manifest.json")))
def test_committed_manifests_are_portable(manifest_file):
    """Release manifests must not contain machine-specific paths or usernames."""
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert data["files"], manifest_file.name
    for entry in data["files"]:
        _assert_portable(entry["path"], PROJECT_ROOT)
        assert entry["path"].startswith("data/raw/")
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    text = manifest_file.read_text(encoding="utf-8")
    assert not USER_DIR.search(text)
    assert not re.search(r"[A-Za-z]:\\\\", text)
