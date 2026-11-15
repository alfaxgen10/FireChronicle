"""
FireChronicle — seasonal baselines and anomaly calculation.

Blueprint §3.4:
  "Define a seasonal anomaly as H(year,month) minus the historical median
   for that same calendar month. Use a declared baseline window."

All baseline windows and thresholds are declared in config.py and must be
fixed BEFORE inspecting results.  Do not add post-hoc configurations.

Scientific limitations recorded in every output
------------------------------------------------
- The 2019–2024 reference period is short (6 years); monthly baselines
  rest on at most 6 observations.  Treat results as indicative.
- Months with has_data=False are excluded from baseline statistics.
  Missing months are NOT treated as confirmed zero activity.
- The elevated_quantile threshold is pre-specified in config.py and must
  not be adjusted to match a desired number of elevated months.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.config import (
    BASELINE_YEAR_END,
    BASELINE_YEAR_START,
    LABEL_CONSISTENTLY_ELEVATED,
    LABEL_INSUFFICIENT_EVIDENCE,
    LABEL_NOT_ELEVATED,
)

logger = logging.getLogger(__name__)

MIN_BASELINE_MONTHS = 3   # minimum non-missing months needed to compute a baseline

# Minimum observations required for a leave-one-year-out threshold.
# LOO removes 1 observation, so we need at least this many BEFORE removal.
MIN_LOO_OBSERVATIONS = 4


def compute_seasonal_baseline(
    agg: pd.DataFrame,
    baseline_start: int = BASELINE_YEAR_START,
    baseline_end:   int = BASELINE_YEAR_END,
) -> pd.DataFrame:
    """
    Compute per-calendar-month historical medians from the baseline window.

    Parameters
    ----------
    agg            : Monthly aggregated DataFrame from aggregate.py
    baseline_start : First year of the baseline window
    baseline_end   : Last year of the baseline window

    Returns
    -------
    DataFrame with one row per month (1–12) containing:
      - month
      - baseline_median       : median occupied_cell_fraction over baseline years
      - baseline_n            : count of months with data used
      - baseline_start / end  : window declaration
      - sufficient_baseline   : whether MIN_BASELINE_MONTHS is met
    """
    baseline_rows = agg[
        (agg["year"] >= baseline_start) &
        (agg["year"] <= baseline_end) &
        (agg["has_data"])   # exclude missing-data months from baseline
    ].copy()

    records = []
    for month in range(1, 13):
        month_data = baseline_rows[baseline_rows["month"] == month]["occupied_cell_fraction"]
        n = int(month_data.notna().sum())
        median_val = float(month_data.median()) if n >= MIN_BASELINE_MONTHS else np.nan
        records.append({
            "month": month,
            "baseline_median": median_val,
            "baseline_n": n,
            "baseline_start": baseline_start,
            "baseline_end": baseline_end,
            "sufficient_baseline": n >= MIN_BASELINE_MONTHS,
        })

    baseline_df = pd.DataFrame(records)
    logger.info(
        "compute_seasonal_baseline: baseline=%d–%d months_with_sufficient_data=%d/12",
        baseline_start, baseline_end,
        int(baseline_df["sufficient_baseline"].sum()),
    )
    return baseline_df


def compute_anomalies(
    agg: pd.DataFrame,
    baseline: pd.DataFrame,
    elevated_quantile: float = 0.75,
) -> pd.DataFrame:
    """
    Merge baseline medians into the monthly series and compute anomalies.

    Parameters
    ----------
    agg               : Monthly aggregated DataFrame
    baseline          : Output of compute_seasonal_baseline()
    elevated_quantile : Pre-specified quantile threshold (config.py)

    Returns
    -------
    DataFrame (agg enriched with anomaly columns):
      - baseline_median         : historical median for that calendar month
      - anomaly                 : occupied_cell_fraction - baseline_median
      - elevated_threshold      : the pre-specified quantile value
      - is_elevated             : bool (anomaly > threshold)
      - anomaly_label           : one of the LABEL_ constants
      - anomaly_note            : provenance note
    """
    df = agg.merge(
        baseline[["month", "baseline_median", "baseline_n",
                  "baseline_start", "baseline_end", "sufficient_baseline"]],
        on="month",
        how="left",
    )

    df["anomaly"] = df["occupied_cell_fraction"] - df["baseline_median"]

    # Compute the elevated threshold PER CALENDAR MONTH from the baseline window.
    #
    # Scientific rationale: fire activity in South Sumatra is strongly seasonal.
    # Using a global quantile (across all 12 calendar months) would cause September
    # (peak season) to be almost always "elevated" and February (low season) to
    # almost never be, regardless of anomalous behaviour within that season.
    #
    # Instead: for each calendar month, compute the quantile of its own historical
    # OCF values across all baseline years.  A month is elevated when its OCF
    # exceeds the within-month quantile threshold.
    #
    # This is consistent with the Blueprint §3.4 "seasonal anomaly" framing.
    # Limitation: with only 2019–2024 (≤ 6 values per month), quantile estimates
    # are highly uncertain.  Results must be labelled as indicative, not definitive.

    per_month_threshold: dict[int, float] = {}
    for cal_month in range(1, 13):
        month_rows = df[
            (df["month"] == cal_month) &
            df["has_data"] &
            df["sufficient_baseline"]
        ]["occupied_cell_fraction"].dropna()
        if len(month_rows) >= MIN_BASELINE_MONTHS:
            per_month_threshold[cal_month] = float(month_rows.quantile(elevated_quantile))
        else:
            per_month_threshold[cal_month] = float("nan")

    # Store the per-month threshold as a column for provenance
    df["elevated_threshold"] = df["month"].map(per_month_threshold)
    df["elevated_quantile_pct"] = elevated_quantile

    def _classify(row: pd.Series) -> tuple[bool, str, str]:
        """Return (is_elevated, label, note)."""
        if not row["has_data"]:
            return False, LABEL_INSUFFICIENT_EVIDENCE, "no_detections"
        if not row["sufficient_baseline"]:
            return False, LABEL_INSUFFICIENT_EVIDENCE, "insufficient_baseline"
        threshold = row["elevated_threshold"]
        if np.isnan(row["occupied_cell_fraction"]) or (
            isinstance(threshold, float) and np.isnan(threshold)
        ):
            return False, LABEL_INSUFFICIENT_EVIDENCE, "nan_value"
        elevated = row["occupied_cell_fraction"] > threshold
        if elevated:
            return True, LABEL_CONSISTENTLY_ELEVATED, "above_month_threshold"
        return False, LABEL_NOT_ELEVATED, "at_or_below_month_threshold"

    classifications = df.apply(_classify, axis=1, result_type="expand")
    classifications.columns = ["is_elevated", "anomaly_label", "anomaly_note"]
    df = pd.concat([df, classifications], axis=1)

    n_sufficient_months = sum(1 for v in per_month_threshold.values() if not np.isnan(v))
    logger.info(
        "compute_anomalies: sensor=%s elevated_q=%.0f%% "
        "calendar_months_with_threshold=%d/12 "
        "elevated_months=%d insufficient=%d",
        df["sensor"].iloc[0] if len(df) > 0 else "?",
        elevated_quantile * 100,
        n_sufficient_months,
        int((df["anomaly_label"] == LABEL_CONSISTENTLY_ELEVATED).sum()),
        int((df["anomaly_label"] == LABEL_INSUFFICIENT_EVIDENCE).sum()),
    )
    return df


# ---------------------------------------------------------------------------
# Leave-one-year-out classification (optional diagnostic)
# ---------------------------------------------------------------------------

def compute_loo_classification(
    agg: pd.DataFrame,
    elevated_quantile: float = 0.75,
    baseline_start: int = BASELINE_YEAR_START,
    baseline_end: int = BASELINE_YEAR_END,
) -> pd.DataFrame:
    """
    Leave-one-year-out (LOO) classification of each year-month.

    For each year Y and calendar month M, this function:
      1. Computes the per-calendar-month quantile threshold using all years
         EXCEPT Y (leave-one-out).
      2. Classifies Y-M as elevated if OCF(Y, M) > LOO_threshold(M, excluding Y).

    Scientific rationale
    --------------------
    The standard ``compute_anomalies`` uses the full baseline to set the
    threshold, which means year Y's own value is included when setting its
    threshold.  This creates a conservative self-inclusion bias: an extreme
    year raises its own bar slightly.

    Simulation (Phase 3 audit) showed the bias changes classification in
    approximately 0% of cases with n=6 and exponential-distribution inputs,
    because with n=6 the quantile estimator changes very little when one
    observation is removed.

    However, LOO is the more principled approach for small baselines, and
    this function provides it as a **diagnostic** (not the default).

    Limitations
    -----------
    - LOO requires at least MIN_LOO_OBSERVATIONS (4) values per calendar
      month after removing one year.  With the 2019–2024 baseline (n≤6),
      many months will have insufficient LOO observations.
    - Results should be compared to the standard classification, not presented
      independently.
    - Self-inclusion bias with n=6 is conservative (makes it harder to classify
      as elevated). With n=6, no ties and q=0.75, LOO and in-sample labels are
      identical by construction. At q=0.90 they can differ: on the real
      2019–2024 data, 3 of 72 MODIS q=0.90 labels change (not -> elevated);
      see scripts/run_loo_diagnostic.py and docs/SCIENTIFIC_AUDIT.md §0.

    Parameters
    ----------
    agg               : Monthly aggregated DataFrame (from aggregate_monthly)
    elevated_quantile : Pre-specified quantile (must match the main analysis)
    baseline_start    : First year of baseline window
    baseline_end      : Last year of baseline window

    Returns
    -------
    DataFrame with columns:
      - period, year, month
      - ocf              : occupied_cell_fraction for this period
      - loo_threshold    : quantile threshold computed excluding this year
      - loo_n            : number of observations used for LOO threshold
      - loo_sufficient   : whether LOO had enough data
      - loo_is_elevated  : bool
      - loo_label        : LABEL_* string
      - agrees_with_standard : whether LOO agrees with compute_anomalies
    """
    all_years = sorted(agg[(agg["year"] >= baseline_start) &
                            (agg["year"] <= baseline_end)]["year"].unique())

    # Pre-compute baseline data grouped by calendar month
    baseline_data = {}
    for cal_month in range(1, 13):
        month_rows = agg[
            (agg["month"] == cal_month) &
            (agg["year"] >= baseline_start) &
            (agg["year"] <= baseline_end) &
            agg["has_data"]
        ][["year", "occupied_cell_fraction"]].dropna(subset=["occupied_cell_fraction"])
        baseline_data[cal_month] = month_rows

    records = []
    for _, row in agg.iterrows():
        year = int(row["year"])
        month = int(row["month"])
        period = row["period"]
        ocf = row.get("occupied_cell_fraction")

        if not row.get("has_data", False) or ocf is None or pd.isna(ocf):
            records.append({
                "period": period, "year": year, "month": month,
                "ocf": None, "loo_threshold": None, "loo_n": 0,
                "loo_sufficient": False, "loo_is_elevated": False,
                "loo_label": LABEL_INSUFFICIENT_EVIDENCE,
                "agrees_with_standard": None,
            })
            continue

        # LOO: exclude this year from the threshold calculation
        month_data = baseline_data.get(month, pd.DataFrame())
        loo_data = month_data[month_data["year"] != year]["occupied_cell_fraction"].dropna()
        loo_n = len(loo_data)

        if loo_n < MIN_LOO_OBSERVATIONS:
            records.append({
                "period": period, "year": year, "month": month,
                "ocf": float(ocf), "loo_threshold": None, "loo_n": loo_n,
                "loo_sufficient": False, "loo_is_elevated": False,
                "loo_label": LABEL_INSUFFICIENT_EVIDENCE,
                "agrees_with_standard": None,
            })
            continue

        loo_threshold = float(loo_data.quantile(elevated_quantile))
        loo_elevated = float(ocf) > loo_threshold
        loo_label = LABEL_CONSISTENTLY_ELEVATED if loo_elevated else LABEL_NOT_ELEVATED

        # Compare with standard label if available
        std_label = row.get("anomaly_label")
        agrees = (std_label == loo_label) if std_label is not None else None

        records.append({
            "period": period, "year": year, "month": month,
            "ocf": float(ocf),
            "loo_threshold": round(loo_threshold, 6),
            "loo_n": loo_n,
            "loo_sufficient": True,
            "loo_is_elevated": loo_elevated,
            "loo_label": loo_label,
            "agrees_with_standard": agrees,
        })

    result = pd.DataFrame(records)
    n_sufficient = int(result["loo_sufficient"].sum())
    n_disagree   = int((result["agrees_with_standard"] == False).sum())
    logger.info(
        "compute_loo_classification: periods_with_loo=%d/%d disagree_with_standard=%d",
        n_sufficient, len(result), n_disagree,
    )
    return result
