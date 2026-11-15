"""
Tests that verify fixture-derived JSON outputs are clearly distinguished
from real NASA-derived outputs.

These tests ensure the frontend cannot accidentally treat fixture data
as validated science.
"""

import json
from pathlib import Path

import pytest

FRONTEND_DATA = Path(__file__).parent.parent / "web" / "public" / "data"
JSON_FILES = ["regions.json", "calendar.json", "sensors.json",
              "reliability.json", "methodology.json"]


def _load(fname):
    path = FRONTEND_DATA / fname
    if not path.exists():
        pytest.skip(f"{fname} not yet generated")
    with open(path) as f:
        return json.load(f)


class TestFixtureGuard:
    def test_all_files_have_processing_version(self):
        """Every contract must declare a processing_version."""
        for fname in JSON_FILES:
            data = _load(fname)
            assert "processing_version" in data, (
                f"{fname} missing 'processing_version'"
            )

    def test_all_files_have_generated_at(self):
        """Every contract must declare a generation timestamp."""
        for fname in JSON_FILES:
            data = _load(fname)
            assert "generated_at" in data, f"{fname} missing 'generated_at'"

    def test_all_files_have_contract_version(self):
        for fname in JSON_FILES:
            data = _load(fname)
            assert "contract_version" in data, f"{fname} missing 'contract_version'"

    def test_fixture_files_have_is_fixture_flag(self):
        """Files with is_fixture=True must have fixture_warning set."""
        for fname in ["regions.json", "calendar.json", "sensors.json"]:
            data = _load(fname)
            if data.get("is_fixture") is True:
                assert data.get("fixture_warning") is not None, (
                    f"{fname} has is_fixture=True but no fixture_warning"
                )
                assert len(data["fixture_warning"]) > 0

    def test_every_file_declares_fixture_status_and_warning(self):
        """All five contracts must carry is_fixture; fixture outputs need a warning."""
        for fname in JSON_FILES:
            data = _load(fname)
            assert "is_fixture" in data, f"{fname} missing is_fixture"
            if data["is_fixture"]:
                assert data.get("fixture_warning"), f"{fname} is fixture but has no warning"

    def test_reliability_has_is_fixture(self):
        """reliability.json must have is_fixture field."""
        data = _load("reliability.json")
        assert "is_fixture" in data

    def test_no_null_contract_version(self):
        for fname in JSON_FILES:
            data = _load(fname)
            assert data["contract_version"] is not None
            assert len(str(data["contract_version"])) > 0

    def test_calendar_missing_data_note_present(self):
        data = _load("calendar.json")
        assert "missing_data_note" in data
        note = data["missing_data_note"].lower()
        assert "null" in note, "missing_data_note must explain null values"

    def test_methodology_has_scientific_guardrails(self):
        data = _load("methodology.json")
        assert "scientific_guardrails" in data
        guardrails = data["scientific_guardrails"]
        assert len(guardrails) >= 3, "At least 3 scientific guardrails expected"
        combined = " ".join(guardrails).lower()
        assert "hotspot" in combined or "detection" in combined
        assert "not" in combined  # guardrails are prohibitive statements

    def test_sensors_harmonization_unsupported(self):
        """sensors.json must not claim harmonization is supported."""
        data = _load("sensors.json")
        diag = data.get("overlap_diagnostics", {})
        assert diag.get("harmonization_supported") is False, (
            "Harmonization must not be enabled without validated holdout data"
        )

    def test_calendar_null_ocf_not_zero_for_no_data_months(self):
        """Months with has_data=False must have null OCF, never 0.0."""
        data = _load("calendar.json")
        for sensor_key, sensor_data in data.get("sensors", {}).items():
            for month_entry in sensor_data.get("months", []):
                if not month_entry["has_data"]:
                    assert month_entry["occupied_cell_fraction"] is None, (
                        f"{sensor_key} period {month_entry['period']}: "
                        f"has_data=False but OCF={month_entry['occupied_cell_fraction']} (not null)"
                    )
