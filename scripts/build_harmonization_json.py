"""Copy the Stage 6E harmonization-evaluation summary into the web data folder.

Reads diagnostics/stage6e/results/results.json (produced by
diagnostics/stage6e/seasonal_comparability.py) and writes
web/public/data/harmonization.json with only the fields the frontend shows.
No values are recomputed here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "diagnostics" / "stage6e" / "results" / "results.json"
TARGET = ROOT / "web" / "public" / "data" / "harmonization.json"

METHODS = {
    "A_seasonal": "Monthly ratio (median of per-year MODIS/VIIRS ratios for each calendar month)",
    "B_global": "Single ratio (one median MODIS/VIIRS ratio for all months)",
    "C_climatology": "No VIIRS information (training-year mean MODIS value for the month)",
}

CONCLUSION = (
    "The experiment evaluates a seasonal predictive relationship between VIIRS and MODIS "
    "occupied-cell fractions. Improved prediction does not establish sensor equivalence, "
    "measurement calibration, validated fusion or sensor-independent fire activity."
)


def main() -> None:
    raw = SOURCE.read_bytes()
    results = json.loads(raw)
    summary = results["summary"]
    robustness = results["robustness"]
    out = {
        "harmonization_evaluation_version": "1.0.0",
        "status": "diagnostic",
        "source": {
            "file": "diagnostics/stage6e/results/results.json",
            "sha256_lf_normalized": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
            "input_calendar_sha256_lf_normalized": results["input"]["sha256_lf_normalized"],
        },
        "definition": {
            "predictor": results["definition"]["predictor"],
            "target": results["definition"]["target"],
            "validation": results["definition"]["validation"],
            "years": results["definition"]["years"],
            "metric": "mean absolute error of occupied-cell fraction",
        },
        "methods": METHODS,
        "mae": {key: summary["mae"][key] for key in METHODS},
        "mae_by_year": {
            year: {key: values[key] for key in METHODS}
            for year, values in summary["mae_by_year"].items()
        },
        "folds_A_better_than_B": robustness["folds_A_better_than_B"],
        "folds_A_better_than_C": robustness["folds_A_better_than_C"],
        "n_evaluated": summary["n_evaluated"],
        "conclusion": CONCLUSION,
        "decision": "MODIS and VIIRS are kept as separate records; no harmonized series is produced.",
    }
    TARGET.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
