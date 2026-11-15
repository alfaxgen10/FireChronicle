"""
FireChronicle — spatial and temporal aggregation.

Aggregates normalized hotspot observations into a monthly, grid-cell-based
activity series.  Each sensor is processed independently; outputs are NEVER
merged into a single combined count at this stage.

Index definition (Blueprint §3.3)
----------------------------------
  occupied_cell_fraction = (cells with >= 1 detection) / (eligible cells)

Calculated per sensor, per month, separately.  The denominator is fixed for a
given (bbox, resolution, convention) and constant across months.

The index counts cells.  It is NOT an area-weighted measure, NOT a burned-area
estimate and NOT a count of unique fires.  Every eligible cell has weight 1,
including boundary cells that extend outside the bounding box.

Grid conventions (approved scientific decision, processing version 0.2.0)
--------------------------------------------------------------------------
Convention B (PRIMARY): every grid cell that intersects the bounding box is
  eligible.  Every in-bounds detection falls in an eligible cell and is
  included.  Cells not fully inside the box ("partial boundary cells") extend
  partly outside it; their number is reported (`partial_boundary_cells`).

Convention A (SENSITIVITY): only cells whose lower-left origin lies in
  [lon_min, lon_max) x [lat_min, lat_max) are eligible.  Detections that fall
  in a boundary strip not covered by any eligible cell are counted in
  `detection_count` and `partial_cell_detections` but not in the occupied-cell
  fraction.

The South Sumatra box has lat_min = -4.9, which is not on a 0.25 or 0.5 degree
grid line, so the conventions differ along the southern edge only (the other
edges are grid-aligned).  Outputs from the two conventions are not
interchangeable; every output row carries `grid_convention`.

Grid assignment
---------------
  cell_lon = floor(longitude / resolution) * resolution
  cell_lat = floor(latitude  / resolution) * resolution
Points on the upper box edges are clamped into the last cell below the edge.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.config import (
    BBOX,
    GRID_CONVENTION_PRIMARY,
    GRID_CONVENTION_SENSITIVITY,
    GRID_RESOLUTION_DEG_PRIMARY,
    SENSOR_MODIS,
    SENSOR_VIIRS,
    YEAR_END,
    YEAR_START,
)

logger = logging.getLogger(__name__)


def _build_grid_index(
    bbox: tuple[float, float, float, float],
    resolution: float,
) -> pd.DataFrame:
    """
    Return a DataFrame of all grid cell origins within the bounding box.

    A cell is included if its origin (lower-left corner) falls strictly within
    [lon_min, lon_max) × [lat_min, lat_max).  Cells whose origins fall outside
    the bbox are excluded from the denominator.

    Parameters
    ----------
    bbox       : (lon_min, lat_min, lon_max, lat_max)
    resolution : Cell size in decimal degrees

    Returns
    -------
    DataFrame with columns [cell_lon, cell_lat]

    Design note
    -----------
    Using np.arange with float steps can accumulate rounding errors.  We
    round each origin to 10 decimal places and then filter strictly against
    the bbox to guarantee the denominator contains only cells that fully or
    partially overlap the region.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    lon_origins = np.round(
        np.arange(
            np.floor(lon_min / resolution) * resolution,
            lon_max,          # exclusive upper bound — cells starting at lon_max are outside
            resolution,
        ),
        decimals=10,
    )
    lat_origins = np.round(
        np.arange(
            np.floor(lat_min / resolution) * resolution,
            lat_max,          # exclusive upper bound
            resolution,
        ),
        decimals=10,
    )
    lon_grid, lat_grid = np.meshgrid(lon_origins, lat_origins)
    grid = pd.DataFrame({
        "cell_lon": lon_grid.ravel(),
        "cell_lat": lat_grid.ravel(),
    })
    # Keep only cells whose origin is within the bbox (handles floor overshoot)
    grid = grid[
        (grid["cell_lon"] >= lon_min) & (grid["cell_lon"] < lon_max) &
        (grid["cell_lat"] >= lat_min) & (grid["cell_lat"] < lat_max)
    ].reset_index(drop=True)
    return grid


_VALID_CONVENTIONS = (GRID_CONVENTION_PRIMARY, GRID_CONVENTION_SENSITIVITY)


def _build_grid_index_b(
    bbox: tuple[float, float, float, float],
    resolution: float,
) -> pd.DataFrame:
    """
    Convention B: every grid cell that intersects the bounding box.

    A cell [o, o + res) intersects the box iff o < upper edge and o + res >
    lower edge, i.e. origins run from floor(min / res) * res up to (but not
    including) the upper edge.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    lon_origins = np.round(np.arange(np.floor(lon_min / resolution) * resolution,
                                     lon_max, resolution), decimals=10)
    lat_origins = np.round(np.arange(np.floor(lat_min / resolution) * resolution,
                                     lat_max, resolution), decimals=10)
    lon_grid, lat_grid = np.meshgrid(lon_origins, lat_origins)
    return pd.DataFrame({"cell_lon": lon_grid.ravel(), "cell_lat": lat_grid.ravel()})


def build_grid(
    bbox: tuple[float, float, float, float],
    resolution: float,
    convention: str = GRID_CONVENTION_PRIMARY,
) -> pd.DataFrame:
    """Return the eligible cell origins for the requested grid convention."""
    if convention == "B":
        return _build_grid_index_b(bbox, resolution)
    if convention == "A":
        return _build_grid_index(bbox, resolution)
    raise ValueError(
        f"Unknown grid convention {convention!r}; expected one of {_VALID_CONVENTIONS}"
    )


def _fully_interior_mask(
    grid: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    resolution: float,
    tol: float = 1e-9,
) -> pd.Series:
    """True for cells lying entirely inside the bounding box."""
    lon_min, lat_min, lon_max, lat_max = bbox
    return (
        (grid["cell_lon"] >= lon_min - tol) & (grid["cell_lon"] + resolution <= lon_max + tol) &
        (grid["cell_lat"] >= lat_min - tol) & (grid["cell_lat"] + resolution <= lat_max + tol)
    )


def grid_cell_counts(
    bbox: tuple[float, float, float, float] = BBOX,
    resolution: float = GRID_RESOLUTION_DEG_PRIMARY,
    convention: str = GRID_CONVENTION_PRIMARY,
) -> dict:
    """Eligible, fully interior and partial boundary cell counts for a convention."""
    grid = build_grid(bbox, resolution, convention)
    interior = int(_fully_interior_mask(grid, bbox, resolution).sum())
    return {
        "convention": convention,
        "resolution_deg": resolution,
        "eligible_cells": len(grid),
        "fully_interior_cells": interior,
        "partial_boundary_cells": len(grid) - interior,
    }


def _assign_grid_cells(
    df: pd.DataFrame,
    resolution: float,
    bbox: tuple[float, float, float, float] | None = None,
) -> pd.DataFrame:
    """
    Add cell_lon / cell_lat columns to a detections DataFrame.

    Points exactly on the upper bbox edges (lon == lon_max or lat == lat_max)
    are nudged into the last valid cell rather than assigned to a cell outside
    the grid.  This matches the half-open interval [lon_min, lon_max) used in
    _build_grid_index.

    Parameters
    ----------
    df         : DataFrame with 'latitude' and 'longitude' float columns.
    resolution : Grid cell size in decimal degrees.
    bbox       : Optional (lon_min, lat_min, lon_max, lat_max) for edge clamping.
    """
    df = df.copy()
    lon = df["longitude"].copy()
    lat = df["latitude"].copy()

    if bbox is not None:
        lon_min, lat_min, lon_max, lat_max = bbox
        # Clamp upper edges into the last valid cell
        at_lon_max = lon >= lon_max
        at_lat_max = lat >= lat_max
        if at_lon_max.any():
            lon = lon.copy()
            lon[at_lon_max] = lon_max - 1e-9
        if at_lat_max.any():
            lat = lat.copy()
            lat[at_lat_max] = lat_max - 1e-9

    df["cell_lon"] = (np.floor(lon / resolution) * resolution).round(10)
    df["cell_lat"] = (np.floor(lat / resolution) * resolution).round(10)
    return df


def build_complete_month_index(
    year_start: int = YEAR_START,
    year_end:   int = YEAR_END,
) -> pd.DataFrame:
    """
    Build a complete year × month skeleton for the supported time window.

    Returns
    -------
    DataFrame with columns [year, month, period]  (period = "YYYY-MM")
    All 12 months × (year_end - year_start + 1) years.
    """
    rows = [
        {"year": y, "month": m, "period": f"{y:04d}-{m:02d}"}
        for y in range(year_start, year_end + 1)
        for m in range(1, 13)
    ]
    return pd.DataFrame(rows)


def aggregate_monthly(
    df: pd.DataFrame,
    sensor: str,
    resolution: float = GRID_RESOLUTION_DEG_PRIMARY,
    bbox: tuple[float, float, float, float] = BBOX,
    year_start: int = YEAR_START,
    year_end:   int = YEAR_END,
    convention: str = GRID_CONVENTION_PRIMARY,
) -> pd.DataFrame:
    """
    Aggregate normalized detections into a monthly activity series.

    convention : "B" (primary: every cell intersecting the bbox) or
                 "A" (sensitivity: cells whose origin lies inside the bbox)

    Output columns: period, year, month, sensor, resolution_deg,
    grid_convention, detection_count (ALL in-bounds detections),
    occupied_cells, total_eligible_cells, partial_boundary_cells,
    partial_cell_detections (detections in cells not fully inside the bbox),
    occupied_cell_fraction, has_data, coverage_note.

    A month with no usable detections has occupied_cell_fraction = NaN and
    has_data = False; this is missing data, not confirmed zero activity.  The
    fraction is a cell count, not an area-weighted or burned-area measure.
    """
    if convention not in _VALID_CONVENTIONS:
        raise ValueError(
            f"Unknown grid convention {convention!r}; expected one of {_VALID_CONVENTIONS}"
        )

    grid = build_grid(bbox, resolution, convention)
    total_eligible_cells = len(grid)
    partial_boundary_cells = grid_cell_counts(bbox, resolution, convention)["partial_boundary_cells"]

    month_index = build_complete_month_index(year_start, year_end)

    if df is None or len(df) == 0:
        logger.warning("aggregate_monthly: empty DataFrame for sensor %s", sensor)
        month_index["sensor"] = sensor
        month_index["resolution_deg"] = resolution
        month_index["grid_convention"] = convention
        month_index["detection_count"] = 0
        month_index["occupied_cells"] = 0
        month_index["partial_cell_detections"] = 0
        month_index["total_eligible_cells"] = total_eligible_cells
        month_index["partial_boundary_cells"] = partial_boundary_cells
        month_index["occupied_cell_fraction"] = np.nan
        month_index["has_data"] = False
        month_index["coverage_note"] = "no_input_data"
        return month_index

    df = _assign_grid_cells(df, resolution, bbox=bbox)

    lon_min, lat_min, lon_max, lat_max = bbox
    in_bbox = (
        (df["longitude"] >= lon_min) & (df["longitude"] <= lon_max) &
        (df["latitude"]  >= lat_min) & (df["latitude"]  <= lat_max)
    )
    df = df[in_bbox].copy()
    if len(df) == 0:
        logger.warning("aggregate_monthly: 0 rows in bbox for sensor %s", sensor)

    count_series = df.groupby(["year", "month"]).size().rename("detection_count")

    # Vectorised cell membership (no per-row Python loop)
    def _keys(frame):
        return pd.MultiIndex.from_arrays(
            [frame["cell_lon"].round(8), frame["cell_lat"].round(8)]
        )

    cell_keys = _keys(df)
    interior_grid = grid[_fully_interior_mask(grid, bbox, resolution)]
    df["_eligible"] = cell_keys.isin(_keys(grid))
    df["_partial"] = ~cell_keys.isin(_keys(interior_grid))
    df_eligible = df[df["_eligible"]]
    df_partial = df[df["_partial"]]

    if len(df_partial) > 0:
        partial_grp = (df_partial.groupby(["year", "month"]).size()
                       .rename("partial_cell_detections").reset_index())
    else:
        partial_grp = pd.DataFrame(columns=["year", "month", "partial_cell_detections"])

    if len(df_eligible) > 0:
        occupied_grp = (
            df_eligible.drop_duplicates(subset=["year", "month", "cell_lon", "cell_lat"])
            .groupby(["year", "month"]).size().rename("occupied_cells").reset_index()
        )
    else:
        occupied_grp = pd.DataFrame(columns=["year", "month", "occupied_cells"])

    agg = (month_index
           .merge(count_series.reset_index(), on=["year", "month"], how="left")
           .merge(occupied_grp, on=["year", "month"], how="left")
           .merge(partial_grp, on=["year", "month"], how="left"))
    for col in ("detection_count", "occupied_cells", "partial_cell_detections"):
        agg[col] = pd.to_numeric(agg[col], errors="coerce").fillna(0).astype(int)

    agg["sensor"] = sensor
    agg["resolution_deg"] = resolution
    agg["grid_convention"] = convention
    agg["total_eligible_cells"] = total_eligible_cells
    agg["partial_boundary_cells"] = partial_boundary_cells
    agg["occupied_cell_fraction"] = np.where(
        agg["occupied_cells"] > 0, agg["occupied_cells"] / total_eligible_cells, np.nan,
    )
    agg["has_data"] = agg["occupied_cells"] > 0
    agg["coverage_note"] = np.where(
        agg["has_data"], "observed", "no_detections_after_quality_filter",
    )

    logger.info(
        "aggregate_monthly: sensor=%s convention=%s res=%.2f months_with_data=%d "
        "detections=%d boundary_cell_detections=%d eligible_cells=%d",
        sensor, convention, resolution, int(agg["has_data"].sum()),
        int(agg["detection_count"].sum()), int(agg["partial_cell_detections"].sum()),
        total_eligible_cells,
    )
    return agg


def grid_geographic_support(
    bbox: tuple[float, float, float, float] = BBOX,
    resolution: float = GRID_RESOLUTION_DEG_PRIMARY,
) -> dict:
    """
    Geographic support of both grid conventions (areas in square degrees, not km2).

    Convention B (PRIMARY): every cell intersecting the bbox.  Covers the whole
        box; partial boundary cells extend outside it.
    Convention A (SENSITIVITY): cells whose origin lies inside the bbox.  A
        boundary strip of the box is not covered.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    a = grid_cell_counts(bbox, resolution, "A")
    b = grid_cell_counts(bbox, resolution, "B")
    n_a, n_b = a["eligible_cells"], b["eligible_cells"]

    bbox_area = (lon_max - lon_min) * (lat_max - lat_min)
    area_a = n_a * resolution * resolution
    area_b = n_b * resolution * resolution
    uncovered_a = bbox_area - a["fully_interior_cells"] * resolution * resolution
    outside_b = area_b - bbox_area

    return {
        "primary_convention": "B",
        "resolution_deg": resolution,
        "bbox_area_sq_deg": round(bbox_area, 6),
        "convention_b_cells": n_b,
        "convention_b_fully_interior_cells": b["fully_interior_cells"],
        "convention_b_partial_boundary_cells": b["partial_boundary_cells"],
        "convention_b_area_sq_deg": round(area_b, 6),
        "convention_b_area_outside_bbox_sq_deg": round(outside_b, 6),
        "convention_a_cells": n_a,
        "convention_a_area_sq_deg": round(area_a, 6),
        "convention_a_bbox_area_not_covered_sq_deg": round(uncovered_a, 6),
        "convention_a_bbox_not_covered_fraction": round(uncovered_a / bbox_area, 6),
        "denominator_ratio_b_over_a": round(n_b / n_a, 6),
    }


def compare_grid_conventions(
    df: pd.DataFrame,
    sensor: str,
    resolution: float = GRID_RESOLUTION_DEG_PRIMARY,
    bbox: tuple[float, float, float, float] = BBOX,
    year_start: int = YEAR_START,
    year_end: int = YEAR_END,
) -> pd.DataFrame:
    """
    Month-by-month comparison of the primary index (Convention B) with the
    sensitivity index (Convention A).  Both come from aggregate_monthly, so the
    only difference is the grid convention.
    """
    agg_b = aggregate_monthly(df, sensor, resolution, bbox, year_start, year_end, convention="B")
    agg_a = aggregate_monthly(df, sensor, resolution, bbox, year_start, year_end, convention="A")

    out = agg_b[["period", "year", "month", "detection_count", "partial_cell_detections",
                 "occupied_cells", "total_eligible_cells", "occupied_cell_fraction"]].rename(
        columns={"occupied_cells": "occupied_cells_b", "total_eligible_cells": "denominator_b",
                 "occupied_cell_fraction": "ocf_b"})
    out["occupied_cells_a"] = agg_a["occupied_cells"].values
    out["denominator_a"] = agg_a["total_eligible_cells"].values
    out["ocf_a"] = agg_a["occupied_cell_fraction"].values
    out["has_data_differs"] = (out["occupied_cells_a"] > 0) != (out["occupied_cells_b"] > 0)
    return out


def aggregate_all(
    normalized: dict[str, Optional[pd.DataFrame]],
    resolution: float = GRID_RESOLUTION_DEG_PRIMARY,
) -> dict[str, pd.DataFrame]:
    """
    Run monthly aggregation for all available sensors.

    Parameters
    ----------
    normalized : Dict from normalize.normalize_all()
    resolution : Grid resolution in degrees

    Returns
    -------
    Dict mapping sensor identifier -> monthly aggregated DataFrame
    """
    results = {}
    for sensor, item in normalized.items():
        if item is None:
            df_norm = None
        else:
            df_norm, _stats = item
        results[sensor] = aggregate_monthly(df_norm, sensor, resolution)
    return results
