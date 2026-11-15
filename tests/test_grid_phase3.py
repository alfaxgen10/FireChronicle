"""
Phase 3 grid geometry verification tests.

Covers:
- Independent mathematical verification of cell counts
- Partial-cell strip treatment at bbox lower latitude boundary
- Consistency between detection_count and occupied_cells
- OCF denominator/numerator consistency
- All four boundary edges

SYNTHETIC DATA ONLY.
"""

import math

import numpy as np
import pandas as pd
import pytest

from pipeline.aggregate import (
    _build_grid_index,
    _assign_grid_cells,
    aggregate_monthly,
)
from pipeline.config import BBOX, SENSOR_MODIS, YEAR_START, YEAR_END


# ---------------------------------------------------------------------------
# Mathematical verification helpers
# ---------------------------------------------------------------------------

def _count_cells_exact(bbox, resolution):
    """
    Count grid cells using integer arithmetic to avoid floating-point errors.
    Returns (n_lon, n_lat, n_total).
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    # Use integer index: cell index i maps to origin = i * resolution
    # Count integers i such that lon_min <= i*res < lon_max
    # i in [ceil(lon_min/res), floor((lon_max-eps)/res)]
    lon_i_min = math.ceil(lon_min / resolution)
    lon_i_max = math.floor((lon_max - 1e-12) / resolution)
    lat_i_min = math.ceil(lat_min / resolution)
    lat_i_max = math.floor((lat_max - 1e-12) / resolution)
    n_lon = max(0, lon_i_max - lon_i_min + 1)
    n_lat = max(0, lat_i_max - lat_i_min + 1)
    return n_lon, n_lat, n_lon * n_lat


class TestGridCellCountVerification:
    """Independent mathematical verification of grid cell counts."""

    def test_025_degree_count_matches_integer_arithmetic(self):
        n_lon, n_lat, expected = _count_cells_exact(BBOX, 0.25)
        actual = len(_build_grid_index(BBOX, 0.25))
        assert actual == expected, (
            f"0.25°: expected {n_lon}×{n_lat}={expected}, got {actual}"
        )

    def test_05_degree_count_matches_integer_arithmetic(self):
        n_lon, n_lat, expected = _count_cells_exact(BBOX, 0.5)
        actual = len(_build_grid_index(BBOX, 0.5))
        assert actual == expected, (
            f"0.5°: expected {n_lon}×{n_lat}={expected}, got {actual}"
        )

    def test_025_degree_specific_counts(self):
        """
        0.25° grid: lon [101.5,106.0) = 18 cells; lat [-4.9,-1.0) = 15 cells.

        lat count derivation:
          ceil(-4.9/0.25) = ceil(-19.6) = -19  → first origin = -19*0.25 = -4.75
          floor((-1.0-eps)/0.25) = floor(-4.0-) = -4  → last origin = -4*0.25 = -1.0? No
          Actually floor((-1.0-1e-12)/0.25) = floor(-4.000...0004) = -5? No, -4.000 -> floor = -4
          Wait: -1.0/0.25 = -4.0, so floor(-4.0 - eps) = floor(-4.000...) = -4
          last_i = -4, last_origin = -4*0.25 = -1.0
          BUT we need origin < lat_max = -1.0, so -1.0 is excluded.
          Hmm: floor((-1.0 - 1e-12)/0.25) with 1e-12 perturbation...
          -1.0000000000010/0.25 = -4.000000000004, floor = -4... still -4.
          But origin -4*0.25 = -1.0 which equals lat_max.  grid filter: origin < lat_max = -1.0.
          -1.0 < -1.0 is False, so it IS excluded. So last valid: -5*0.25 = -1.25.
          lat_i from -19 to -5: count = -5 - (-19) + 1 = 15. ✓
        """
        n_lon, n_lat, total = _count_cells_exact(BBOX, 0.25)
        assert n_lon == 18, f"Expected 18 lon cells, got {n_lon}"
        assert n_lat == 15, f"Expected 15 lat cells, got {n_lat}"
        assert total == 270

    def test_05_degree_specific_counts(self):
        """
        0.5° grid: lon [101.5,106.0) = 9 cells; lat [-4.9,-1.0) = 7 cells.

        lat derivation:
          ceil(-4.9/0.5) = ceil(-9.8) = -9  → first origin = -9*0.5 = -4.5
          Last valid: floor((-1.0-eps)/0.5) = floor(-2.000...eps) = -3 → origin = -1.5
          count = -3 - (-9) + 1 = 7. ✓
        """
        n_lon, n_lat, total = _count_cells_exact(BBOX, 0.5)
        assert n_lon == 9, f"Expected 9 lon cells, got {n_lon}"
        assert n_lat == 7, f"Expected 7 lat cells, got {n_lat}"
        assert total == 63

    def test_grid_first_lat_origin_025(self):
        """First latitude origin must be first grid line >= lat_min."""
        grid = _build_grid_index(BBOX, 0.25)
        lat_min = BBOX[1]
        first_lat = grid["cell_lat"].min()
        # First origin must be >= lat_min and within one resolution step
        assert first_lat >= lat_min
        assert first_lat < lat_min + 0.25

    def test_grid_first_lat_origin_05(self):
        grid = _build_grid_index(BBOX, 0.5)
        lat_min = BBOX[1]
        first_lat = grid["cell_lat"].min()
        assert first_lat >= lat_min
        assert first_lat < lat_min + 0.5

    def test_all_cell_origins_are_grid_multiples(self):
        """Every cell origin must be an exact multiple of the resolution."""
        for res in [0.25, 0.5]:
            grid = _build_grid_index(BBOX, res)
            for col in ["cell_lon", "cell_lat"]:
                residuals = (grid[col] / res) % 1
                # Allow floating-point tolerance of 1e-9
                bad = residuals[(residuals > 1e-9) & (residuals < 1 - 1e-9)]
                assert len(bad) == 0, (
                    f"Resolution {res}: {len(bad)} {col} origins not multiples of {res}"
                )


class TestPartialCellStrip:
    """
    SENSITIVITY convention A (no longer primary since processing version 0.2.0).
    Verify the partial-cell treatment at bbox lower boundary under Convention A.

    The strip lat in [-4.9, -4.75) at 0.25° is inside the bbox but its
    detections get assigned to cell origin -5.0 (below the grid).
    These detections must appear in detection_count but NOT in occupied_cells.
    """

    def _make_norm_row(self, lat, lon, year=2021, month=9):
        """Return a minimal normalized-style DataFrame row."""
        return {
            "latitude": lat, "longitude": lon,
            "year": year, "month": month,
            "acq_datetime_utc": pd.Timestamp(f"{year}-{month:02d}-15 06:30"),
            "sensor": SENSOR_MODIS,
            "frp": 20.0, "brightness": 320.0,
            "daynight": "D", "product_version": "6.1NRT",
            "_source_file": "test.csv",
        }

    def test_strip_detection_in_detection_count_not_occupied(self):
        """
        A detection at lat=-4.85 (inside bbox, inside partial strip) must:
        - contribute to detection_count
        - NOT contribute to occupied_cells (cell origin -5.0 outside grid)
        """
        df = pd.DataFrame([self._make_norm_row(-4.85, 103.5)])
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25, convention="A")
        sep = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep["detection_count"].iloc[0] == 1, "Strip detection must appear in detection_count"
        assert sep["occupied_cells"].iloc[0] == 0, "Strip detection must NOT appear in occupied_cells"
        assert sep["partial_cell_detections"].iloc[0] == 1, "Must be counted in partial_cell_detections"
        # has_data is False because no grid-aligned cells occupied
        assert sep["has_data"].iloc[0] == False
        # OCF must be null
        assert pd.isna(sep["occupied_cell_fraction"].iloc[0])

    def test_non_strip_detection_fully_counted(self):
        """A detection inside the grid (lat=-3.0) must count in both."""
        df = pd.DataFrame([self._make_norm_row(-3.0, 103.5)])
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25, convention="A")
        sep = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep["detection_count"].iloc[0] == 1
        assert sep["occupied_cells"].iloc[0] == 1
        assert sep["has_data"].iloc[0] == True
        assert not pd.isna(sep["occupied_cell_fraction"].iloc[0])

    def test_mixed_strip_and_grid_detections(self):
        """Month with both strip and grid detections: OCF uses only grid ones."""
        rows = [
            self._make_norm_row(-4.85, 103.5),  # strip
            self._make_norm_row(-3.0, 103.5),   # in-grid
            self._make_norm_row(-2.5, 104.0),   # in-grid, different cell
        ]
        df = pd.DataFrame(rows)
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25, convention="A")
        sep = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep["detection_count"].iloc[0] == 3
        assert sep["occupied_cells"].iloc[0] == 2  # only 2 grid-aligned
        assert sep["partial_cell_detections"].iloc[0] == 1

    def test_partial_cell_column_zero_when_no_strip_detections(self):
        """When all detections are in the grid, partial_cell_detections must be 0."""
        df = pd.DataFrame([self._make_norm_row(-2.0, 103.0)])
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25, convention="A")
        sep = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep["partial_cell_detections"].iloc[0] == 0

    def test_05_degree_strip_wider(self):
        """At 0.5°, the strip extends from -4.9 to -4.5 — wider but same logic."""
        # lat=-4.6 is in strip [-4.9, -4.5) for 0.5° grid
        df = pd.DataFrame([self._make_norm_row(-4.6, 103.5)])
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.5, convention="A")
        sep = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep["detection_count"].iloc[0] == 1
        assert sep["occupied_cells"].iloc[0] == 0
        assert sep["partial_cell_detections"].iloc[0] == 1


class TestAllFourBoundaryEdges:
    """Comprehensive boundary behavior tests at all four bbox edges."""

    def _agg_single(self, lat, lon, resolution=0.25, convention="B"):
        df = pd.DataFrame([{
            "latitude": lat, "longitude": lon,
            "year": 2021, "month": 9,
            "acq_datetime_utc": pd.Timestamp("2021-09-15 06:30"),
            "sensor": SENSOR_MODIS,
            "frp": 20.0, "brightness": 320.0,
            "daynight": "D", "product_version": "6.1NRT",
            "_source_file": "test.csv",
        }])
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=resolution, convention=convention)
        return agg[(agg["year"] == 2021) & (agg["month"] == 9)].iloc[0]

    def test_left_edge_lon_min_inside_grid(self):
        """lon=101.5 (bbox left edge, on grid line) → first valid cell."""
        row = self._agg_single(lat=-2.5, lon=101.5)
        assert row["occupied_cells"] == 1

    def test_right_edge_lon_max_clamped(self):
        """lon=106.0 (bbox right edge) → clamped to last valid cell."""
        row = self._agg_single(lat=-2.5, lon=106.0)
        assert row["occupied_cells"] == 1

    def test_top_edge_lat_max_clamped(self):
        """lat=-1.0 (bbox top edge) → clamped to last valid cell."""
        row = self._agg_single(lat=-1.0, lon=103.5)
        assert row["occupied_cells"] == 1

    def test_bottom_edge_lat_min_in_partial_strip_convention_a(self):
        """Convention A (sensitivity): lat=-4.9 is in the uncovered strip, not in the fraction."""
        row = self._agg_single(lat=-4.9, lon=103.5, convention="A")
        assert row["occupied_cells"] == 0
        assert row["partial_cell_detections"] == 1

    def test_bottom_edge_lat_min_included_convention_b(self):
        """Convention B (primary): lat=-4.9 falls in a partial boundary cell and IS counted."""
        row = self._agg_single(lat=-4.9, lon=103.5, convention="B")
        assert row["occupied_cells"] == 1
        assert row["partial_cell_detections"] == 1

    def test_outside_bbox_excluded(self):
        """Detections outside bbox are excluded entirely by bbox clip."""
        for lat, lon in [(-6.0, 103.5), (0.0, 103.5), (-2.5, 100.0), (-2.5, 107.0)]:
            row = self._agg_single(lat=lat, lon=lon)
            assert row["detection_count"] == 0, f"({lat},{lon}) should be outside bbox"

    def test_just_inside_all_edges(self):
        """Points just inside each edge should all produce occupied_cells=1."""
        cases = [
            (-2.5, 101.5 + 0.001),   # just right of left edge
            (-2.5, 106.0 - 0.001),   # just left of right edge
            (-1.0 - 0.001, 103.5),   # just below top edge
        ]
        for lat, lon in cases:
            row = self._agg_single(lat=lat, lon=lon)
            assert row["occupied_cells"] == 1, (
                f"({lat},{lon}) should produce 1 occupied cell"
            )
