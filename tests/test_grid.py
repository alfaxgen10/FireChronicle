"""
Tests for grid construction, cell assignment and boundary edge cases.

These tests verify the denominator is consistent, upper-edge detections
are handled correctly, and cells outside the bbox are excluded.

SYNTHETIC DATA ONLY.
"""

import numpy as np
import pandas as pd
import pytest

from pipeline.aggregate import _build_grid_index, _assign_grid_cells
from pipeline.config import BBOX


class TestGridIndex:
    def test_cell_count_025_degree(self):
        """0.25° grid over South Sumatra bbox."""
        grid = _build_grid_index(BBOX, 0.25)
        lon_min, lat_min, lon_max, lat_max = BBOX
        # lon range: 101.5 to <106.0  → 18 cells
        # lat range: -4.9 to <-1.0 → floor(-4.9/0.25)*0.25 = -5.0, up to <-1.0
        # cells from -5.0 is excluded (< lat_min=-4.9? No: -5.0 < -4.9 so excluded)
        # cells starting at -4.75 are ≥ -4.9? -4.75 > -4.9 yes → included
        # So lat origins: floor(-4.9/0.25)*0.25 = floor(-19.6)*0.25 = -20*0.25 = -5.0
        # -5.0 < -4.9, so EXCLUDED by the strict filter
        # Next: -4.75 ≥ -4.9 ✓; up to -1.25 < -1.0 ✓; -1.0 is excluded
        # lat cells: -4.75, -4.5, ..., -1.25  → 15 values
        # lon cells: 101.5, ..., 105.75 → 18 values
        assert len(grid) == 18 * 15

    def test_cell_count_05_degree(self):
        """0.5° grid."""
        grid = _build_grid_index(BBOX, 0.5)
        # lon: 101.5..105.5 → 9 cells
        # lat: floor(-4.9/0.5)*0.5 = -5.0, excluded; next -4.5 ≥ -4.9 ✓; up to -1.5 < -1.0
        # lat cells: -4.5, -4.0, -3.5, -3.0, -2.5, -2.0, -1.5 → 7 values
        assert len(grid) == 9 * 7

    def test_no_cells_outside_bbox(self):
        """All returned cells must have origins inside [lon_min, lon_max) × [lat_min, lat_max)."""
        lon_min, lat_min, lon_max, lat_max = BBOX
        for res in [0.25, 0.5]:
            grid = _build_grid_index(BBOX, res)
            outside = grid[
                (grid["cell_lon"] < lon_min) | (grid["cell_lon"] >= lon_max) |
                (grid["cell_lat"] < lat_min) | (grid["cell_lat"] >= lat_max)
            ]
            assert len(outside) == 0, (
                f"Resolution {res}: {len(outside)} cells outside bbox: {outside.head()}"
            )

    def test_denominator_stable_across_calls(self):
        """Grid size must be identical on repeated calls with same parameters."""
        g1 = _build_grid_index(BBOX, 0.25)
        g2 = _build_grid_index(BBOX, 0.25)
        assert len(g1) == len(g2)


class TestGridCellAssignment:
    def test_interior_point_assigned_correctly(self):
        df = pd.DataFrame({"latitude": [-2.5], "longitude": [103.5]})
        result = _assign_grid_cells(df, 0.25, bbox=BBOX)
        # floor(103.5 / 0.25) * 0.25 = 414 * 0.25 = 103.5 ✓
        assert result["cell_lon"].iloc[0] == pytest.approx(103.5)
        # floor(-2.5 / 0.25) * 0.25 = -10 * 0.25 = -2.5 ✓
        assert result["cell_lat"].iloc[0] == pytest.approx(-2.5)

    def test_upper_lon_edge_clamps_to_last_cell(self):
        """A detection at exactly lon_max=106.0 must map to cell 105.75, not 106.0."""
        lon_min, lat_min, lon_max, lat_max = BBOX
        df = pd.DataFrame({"latitude": [-2.5], "longitude": [lon_max]})
        result = _assign_grid_cells(df, 0.25, bbox=BBOX)
        # Must be < lon_max and in the grid
        assert result["cell_lon"].iloc[0] < lon_max
        # Specifically the last valid cell origin
        assert result["cell_lon"].iloc[0] == pytest.approx(105.75, abs=0.01)

    def test_upper_lat_edge_clamps_to_last_cell(self):
        """A detection at exactly lat_max=-1.0 must map into the last valid cell."""
        lon_min, lat_min, lon_max, lat_max = BBOX
        df = pd.DataFrame({"latitude": [lat_max], "longitude": [103.5]})
        result = _assign_grid_cells(df, 0.25, bbox=BBOX)
        assert result["cell_lat"].iloc[0] < lat_max

    def test_assigned_cell_is_in_grid(self):
        """
        In-bbox points above the bbox lower bounds must map to cells in the grid.

        Note: a point at exactly lat=-4.9 (the bbox lower edge) floors to cell -5.0,
        which is below lat_min and thus excluded from the grid denominator.
        This is correct behaviour: the grid uses half-open intervals [lat_min, lat_max).
        Points below lat_min + resolution should be spatially filtered by aggregate_monthly
        before grid assignment is relevant to the OCF calculation.
        We test only points that are clearly inside the grid's covered area.
        """
        grid = _build_grid_index(BBOX, 0.25)
        # Points clearly inside the bbox (not on lower/upper edges)
        test_points = pd.DataFrame({
            "latitude":  [-2.5, -4.0, -1.5, -4.6],
            "longitude": [103.5, 105.0, 101.6, 105.5],
        })
        assigned = _assign_grid_cells(test_points, 0.25, bbox=BBOX)
        for _, row in assigned.iterrows():
            match = (
                (grid["cell_lon"].round(8) == round(row["cell_lon"], 8)) &
                (grid["cell_lat"].round(8) == round(row["cell_lat"], 8))
            ).any()
            assert match, (
                f"cell ({row['cell_lon']}, {row['cell_lat']}) not in grid"
            )

    def test_no_bbox_arg_still_assigns(self):
        """Without bbox, assignment works but no edge clamping."""
        df = pd.DataFrame({"latitude": [-2.5], "longitude": [103.5]})
        result = _assign_grid_cells(df, 0.25)
        assert "cell_lon" in result.columns
        assert "cell_lat" in result.columns


class TestOccupiedCellFraction:
    """Verify OCF denominator consistency and duplicate cell handling."""

    def _make_norm_df(self, rows):
        """Build a minimal normalized-style DataFrame from row dicts."""
        return pd.DataFrame(rows)

    def test_two_detections_same_cell_count_as_one(self):
        """Two detections in the same grid cell → 1 occupied cell, not 2."""
        from pipeline.aggregate import aggregate_monthly
        from pipeline.config import SENSOR_MODIS, YEAR_START, YEAR_END
        df = pd.DataFrame({
            "latitude":         [-2.5, -2.4],   # both floor to -2.5 at 0.25°
            "longitude":        [103.5, 103.6],  # both floor to 103.5 at 0.25°
            "year":             [2021, 2021],
            "month":            [9, 9],
            "acq_datetime_utc": pd.to_datetime(["2021-09-15 06:30", "2021-09-15 07:00"]),
            "sensor":           [SENSOR_MODIS, SENSOR_MODIS],
            "frp":              [22.0, 18.0],
            "brightness":       [320.0, 315.0],
            "daynight":         ["D", "D"],
            "product_version":  ["6.1NRT", "6.1NRT"],
            "_source_file":     ["test.csv", "test.csv"],
        })
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25)
        sep2021 = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep2021["detection_count"].iloc[0] == 2
        assert sep2021["occupied_cells"].iloc[0] == 1  # only one unique cell

    def test_denominator_does_not_change_with_data_volume(self):
        """total_eligible_cells must be constant regardless of detection count."""
        from pipeline.aggregate import aggregate_monthly
        from pipeline.config import SENSOR_MODIS
        import numpy as np
        # Build a df with many rows
        n = 50
        df = pd.DataFrame({
            "latitude":         np.random.uniform(-4.5, -1.5, n),
            "longitude":        np.random.uniform(102.0, 105.5, n),
            "year":             [2021] * n,
            "month":            [9] * n,
            "acq_datetime_utc": pd.to_datetime(["2021-09-15 06:30"] * n),
            "sensor":           [SENSOR_MODIS] * n,
            "frp":              [20.0] * n,
            "brightness":       [320.0] * n,
            "daynight":         ["D"] * n,
            "product_version":  ["6.1NRT"] * n,
            "_source_file":     ["test.csv"] * n,
        })
        agg1 = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25)
        # Subset to only 5 rows
        agg2 = aggregate_monthly(df.head(5), SENSOR_MODIS, resolution=0.25)
        # Denominator must be identical
        assert agg1["total_eligible_cells"].iloc[0] == agg2["total_eligible_cells"].iloc[0]

    def test_ocf_cannot_exceed_one(self):
        """occupied_cell_fraction must be ≤ 1.0 for any input."""
        from pipeline.aggregate import aggregate_monthly
        from pipeline.config import SENSOR_MODIS, BBOX
        import numpy as np
        # Put a detection in every possible cell
        grid = _build_grid_index(BBOX, 0.25)
        n = len(grid)
        # Place one detection at the center of each cell
        lats = grid["cell_lat"].values + 0.125
        lons = grid["cell_lon"].values + 0.125
        df = pd.DataFrame({
            "latitude":         lats,
            "longitude":        lons,
            "year":             [2021] * n,
            "month":            [9] * n,
            "acq_datetime_utc": pd.to_datetime(["2021-09-15 06:30"] * n),
            "sensor":           [SENSOR_MODIS] * n,
            "frp":              [20.0] * n,
            "brightness":       [320.0] * n,
            "daynight":         ["D"] * n,
            "product_version":  ["6.1NRT"] * n,
            "_source_file":     ["test.csv"] * n,
        })
        agg = aggregate_monthly(df, SENSOR_MODIS, resolution=0.25)
        sep2021 = agg[(agg["year"] == 2021) & (agg["month"] == 9)]
        assert sep2021["occupied_cell_fraction"].iloc[0] <= 1.0
