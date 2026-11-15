"""
FireChronicle — MODIS/VIIRS overlap diagnostics.

This module computes quantitative comparisons between MODIS and VIIRS
monthly aggregates over their common observation period.

Scientific scope (Blueprint §3.2 steps 5–6, Proposal §6 steps 3–4)
--------------------------------------------------------------------
Step 1: Identify the common overlap period (months where both sensors
        have data after quality filtering).

Step 2: Compute side-by-side statistics for all overlap months:
        - Both sensors' occupied_cell_fraction values
        - Ratio VIIRS/MODIS (observation-level, NOT a calibration factor)
        - Rank correlation (Spearman) of seasonal patterns
        - Mean absolute difference

Step 3: Assess comparability:
        - Are seasonal patterns correlated?
        - Are there systematic level differences?
        - Are there apparent discontinuities?

Step 4: Decide whether cautious harmonization is supportable.
        Conservative default: return separate series with documented
        diagnostics.  Do NOT fit a calibration model unless real data
        with an adequate holdout period are available and the diagnostics
        support it.

Scientific limitations (always reported)
-----------------------------------------
- MODIS pixel resolution ≈ 1 km; VIIRS ≈ 375 m.  At the same 0.25° grid,
  VIIRS detects smaller fires that MODIS may miss.
- Overpass times differ between Terra, Aqua (MODIS) and NOAA-20 (VIIRS J1).
  Diurnal fire behaviour means sensors may observe different fire stages.
- The overlap window (2019–2024 at most) is too short to separate sensor
  differences from interannual climate variability.
- A simple VIIRS/MODIS ratio is an observation-level statistic, not a
  physically validated calibration factor.
- Harmonization is flagged as UNSUPPORTED unless explicit validation data
  are provided.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS

logger = logging.getLogger(__name__)


@dataclass
class OverlapDiagnostics:
    """
    Results of MODIS–VIIRS overlap comparison.

    All values are computed from occupied_cell_fraction series.
    """
    n_overlap_months: int = 0
    overlap_start: Optional[str] = None
    overlap_end: Optional[str] = None

    # Descriptive statistics over the common overlap period
    modis_mean_ocf: Optional[float] = None
    viirs_mean_ocf: Optional[float] = None
    mean_ratio_viirs_to_modis: Optional[float] = None   # observation-level only
    median_ratio_viirs_to_modis: Optional[float] = None

    # Correlation of monthly patterns
    spearman_rho: Optional[float] = None
    spearman_p: Optional[float] = None

    # Agreement
    mean_absolute_difference: Optional[float] = None

    # Harmonization decision
    harmonization_supported: bool = False
    harmonization_note: str = ""

    # Per-month detail rows
    detail: list[dict] = field(default_factory=list)

    # Limitations always reported
    limitations: list[str] = field(default_factory=lambda: [
        "MODIS (~1 km) and VIIRS (~375 m) have different native pixel resolutions; "
        "VIIRS detects more small fires at the same grid resolution.",
        "Terra, Aqua (MODIS) and NOAA-20 (VIIRS J1) have different equatorial "
        "crossing times; diurnal fire behaviour affects what each sensor observes.",
        "The overlap window (2019-2024) is too short to separate sensor differences "
        "from interannual climate variability.",
        "ratio_viirs_to_modis is an observation-level statistic, NOT a calibration factor.",
        "Harmonization is not applied unless explicitly validated with holdout data.",
    ])


def compute_overlap_diagnostics(
    agg_modis: pd.DataFrame,
    agg_viirs: pd.DataFrame,
    min_overlap_months: int = 6,
) -> OverlapDiagnostics:
    """
    Compute MODIS–VIIRS overlap diagnostics from monthly aggregated DataFrames.

    Parameters
    ----------
    agg_modis           : Output of aggregate_monthly() for MODIS
    agg_viirs           : Output of aggregate_monthly() for VIIRS
    min_overlap_months  : Minimum months with data in both sensors to report
                          statistics (fewer → returns diagnostics with
                          harmonization_supported=False).

    Returns
    -------
    OverlapDiagnostics dataclass
    """
    diag = OverlapDiagnostics()

    # Identify periods where both sensors have data
    modis_data = agg_modis[agg_modis["has_data"]][["period", "occupied_cell_fraction"]].copy()
    viirs_data = agg_viirs[agg_viirs["has_data"]][["period", "occupied_cell_fraction"]].copy()

    modis_data = modis_data.rename(columns={"occupied_cell_fraction": "modis_ocf"})
    viirs_data = viirs_data.rename(columns={"occupied_cell_fraction": "viirs_ocf"})

    overlap = modis_data.merge(viirs_data, on="period", how="inner")

    diag.n_overlap_months = len(overlap)

    if len(overlap) == 0:
        diag.harmonization_note = (
            "No common months with data for both sensors. "
            "Overlap comparison cannot be performed."
        )
        logger.warning("compute_overlap_diagnostics: no overlap months found")
        return diag

    if len(overlap) < min_overlap_months:
        diag.harmonization_note = (
            f"Only {len(overlap)} overlap months — fewer than the minimum {min_overlap_months} "
            f"required to compute reliable statistics."
        )
        logger.warning(
            "compute_overlap_diagnostics: insufficient overlap (%d < %d months)",
            len(overlap), min_overlap_months,
        )

    overlap = overlap.sort_values("period").reset_index(drop=True)
    diag.overlap_start = overlap["period"].iloc[0]
    diag.overlap_end   = overlap["period"].iloc[-1]

    m_ocf = overlap["modis_ocf"].values
    v_ocf = overlap["viirs_ocf"].values

    diag.modis_mean_ocf = float(np.mean(m_ocf))
    diag.viirs_mean_ocf = float(np.mean(v_ocf))

    # Ratio — only where MODIS > 0 (avoid division by zero)
    valid_ratio = overlap[overlap["modis_ocf"] > 0].copy()
    if len(valid_ratio) > 0:
        ratios = valid_ratio["viirs_ocf"].values / valid_ratio["modis_ocf"].values
        diag.mean_ratio_viirs_to_modis   = float(np.mean(ratios))
        diag.median_ratio_viirs_to_modis = float(np.median(ratios))
    else:
        diag.mean_ratio_viirs_to_modis   = None
        diag.median_ratio_viirs_to_modis = None

    # Spearman rank correlation — requires ≥ 3 paired observations
    if len(overlap) >= 3:
        rho, pval = scipy_stats.spearmanr(m_ocf, v_ocf)
        diag.spearman_rho = float(rho) if not np.isnan(rho) else None
        diag.spearman_p   = float(pval) if not np.isnan(pval) else None
    else:
        diag.spearman_rho = None
        diag.spearman_p   = None

    diag.mean_absolute_difference = float(np.mean(np.abs(v_ocf - m_ocf)))

    # Harmonization decision
    # Conservative: harmonization is UNSUPPORTED unless:
    # (a) ≥ 12 overlap months, (b) Spearman |rho| > 0.6, (c) ratio is stable.
    # With 2019-2024 data the overlap is at most 72 months, but temporal
    # holdout validation has not been performed.
    # Policy: always flag as unsupported at this pipeline stage.
    diag.harmonization_supported = False
    diag.harmonization_note = (
        "Harmonization not applied. "
        "Separate sensor series are retained. "
        "To apply cautious harmonization, provide a temporal holdout validation "
        "and confirm that the ratio is stable across seasons."
    )

    # Build per-month detail
    for _, row in overlap.iterrows():
        m = float(row["modis_ocf"])
        v = float(row["viirs_ocf"])
        ratio = round(v / m, 4) if m > 0 else None
        abs_diff = round(abs(v - m), 6)
        diag.detail.append({
            "period":           row["period"],
            "modis_ocf":        round(m, 6),
            "viirs_ocf":        round(v, 6),
            "ratio_viirs_modis": ratio,
            "abs_difference":   abs_diff,
        })

    logger.info(
        "compute_overlap_diagnostics: n_overlap=%d modis_mean=%.4f viirs_mean=%.4f "
        "spearman_rho=%s mad=%.4f",
        diag.n_overlap_months,
        diag.modis_mean_ocf or 0,
        diag.viirs_mean_ocf or 0,
        f"{diag.spearman_rho:.3f}" if diag.spearman_rho is not None else "N/A",
        diag.mean_absolute_difference or 0,
    )
    return diag


def diagnostics_to_dict(diag: OverlapDiagnostics) -> dict:
    """
    Serialise an OverlapDiagnostics instance to a JSON-compatible dict.
    NaN values are converted to None.
    """
    def _f(v):
        if v is None:
            return None
        if isinstance(v, float) and np.isnan(v):
            return None
        return v

    return {
        "n_overlap_months":            diag.n_overlap_months,
        "overlap_start":               diag.overlap_start,
        "overlap_end":                 diag.overlap_end,
        "modis_mean_ocf":              _f(diag.modis_mean_ocf),
        "viirs_mean_ocf":              _f(diag.viirs_mean_ocf),
        "mean_ratio_viirs_to_modis":   _f(diag.mean_ratio_viirs_to_modis),
        "median_ratio_viirs_to_modis": _f(diag.median_ratio_viirs_to_modis),
        "spearman_rho":                _f(diag.spearman_rho),
        "spearman_p":                  _f(diag.spearman_p),
        "mean_absolute_difference":    _f(diag.mean_absolute_difference),
        "harmonization_supported":     diag.harmonization_supported,
        "harmonization_note":          diag.harmonization_note,
        "detail":                      diag.detail,
        "limitations":                 diag.limitations,
    }
