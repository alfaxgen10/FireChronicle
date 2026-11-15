"""
FireChronicle scientific pipeline package.

Modules
-------
config      — constants, bounding boxes, processing parameters
ingest      — raw NASA FIRMS CSV loading and manifest recording
validate    — schema, coordinate, date and quality checks
normalize   — column standardisation and UTC timestamp handling
aggregate   — monthly grid-cell aggregation, sensor-specific series
harmonize   — overlap diagnostics and optional cautious calibration
baseline    — seasonal medians, anomalies and coverage checks
reliability — sensitivity analysis across predefined configurations
export      — versioned JSON and Parquet outputs for the frontend
"""
