import json

from pipeline import export as export_module
from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS


def _write_manifest(directory, sensor, versions, source_types):
    (directory / f"{sensor}_manifest.json").write_text(
        json.dumps({
            "sensor": sensor,
            "files": [
                {"product_versions": [version], "source_type": source_type}
                for version, source_type in zip(versions, source_types)
            ],
        }),
        encoding="utf-8",
    )


def test_real_methodology_discloses_modis_versions_and_source_types(tmp_path, monkeypatch):
    manifests = tmp_path / "manifests"
    output = tmp_path / "public" / "data"
    manifests.mkdir()
    output.mkdir(parents=True)
    _write_manifest(manifests, SENSOR_MODIS, ["6.03", "61.03", "6.1NRT"], ["archive", "archive", "nrt"])
    _write_manifest(manifests, SENSOR_VIIRS, ["2.0", "2.0"], ["archive", "nrt"])
    monkeypatch.setattr(export_module, "DATA_MANIFESTS", manifests)
    monkeypatch.setattr(export_module, "FRONTEND_DATA", output)

    export_module.export_methodology(is_fixture=False)

    methodology = json.loads((output / "methodology.json").read_text(encoding="utf-8"))
    modis = next(source for source in methodology["data_sources"] if source["sensor"] == SENSOR_MODIS)
    assert modis["product"] == "MODIS Collection 6 and 6.1 Active Fire"
    assert modis["product_versions"] == ["6.03", "6.1NRT", "61.03"]
    assert modis["source_types"] == ["archive", "nrt"]
    assert modis["source_versions_by_type"] == {
        "archive": ["6.03", "61.03"],
        "nrt": ["6.1NRT"],
    }
    assert "2019–2024" in modis["provenance_note"]


def test_fixture_methodology_does_not_inherit_real_manifest_provenance(tmp_path, monkeypatch):
    output = tmp_path / "public" / "data"
    output.mkdir(parents=True)
    monkeypatch.setattr(export_module, "DATA_MANIFESTS", tmp_path / "missing-manifests")
    monkeypatch.setattr(export_module, "FRONTEND_DATA", output)

    export_module.export_methodology(is_fixture=True)

    methodology = json.loads((output / "methodology.json").read_text(encoding="utf-8"))
    modis = next(source for source in methodology["data_sources"] if source["sensor"] == SENSOR_MODIS)
    assert methodology["is_fixture"] is True
    assert modis["product"] == "MODIS Active Fire"
    assert modis["product_versions"] == []
    assert modis["source_types"] == []
    assert modis["source_versions_by_type"] == {}
