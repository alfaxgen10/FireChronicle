"""
Shared pytest fixtures for FireChronicle tests.

All DataFrames loaded here are SYNTHETIC FIXTURES.
They must never be treated as or compared to real NASA data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent.parent / "data" / "fixtures"


@pytest.fixture
def modis_raw_df() -> pd.DataFrame:
    """Raw string-typed MODIS fixture as loaded from CSV."""
    path = FIXTURES / "modis_sample.csv"
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.lower()
    df["_source_file"] = "modis_sample.csv"
    df["_sensor"]      = "MODIS_C61"
    return df


@pytest.fixture
def viirs_raw_df() -> pd.DataFrame:
    """Raw string-typed VIIRS fixture as loaded from CSV."""
    path = FIXTURES / "viirs_sample.csv"
    df = pd.read_csv(path, dtype=str)
    df.columns = df.columns.str.lower()
    df["_source_file"] = "viirs_sample.csv"
    df["_sensor"]      = "VIIRS_J1_C2"
    return df
