import { z } from "zod";

const metadata = {
  contract_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  processing_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  generated_at: z.string().datetime({ offset: true }),
  is_fixture: z.boolean(),
  fixture_warning: z.string().nullable().optional(),
};

const monthSchema = z.object({
  period: z.string().regex(/^\d{4}-\d{2}$/),
  year: z.number().int(),
  month: z.number().int().min(1).max(12),
  detection_count: z.number().int().nonnegative(),
  occupied_cell_fraction: z.number().min(0).max(1).nullable(),
  has_data: z.boolean(),
  coverage_note: z.string(),
  baseline_median: z.number().nullable(),
  anomaly: z.number().nullable(),
  is_elevated: z.boolean(),
  anomaly_label: z.string(),
  elevated_threshold: z.number().nullable(),
  grid_convention: z.string(),
  occupied_cells: z.number().int().nonnegative(),
  total_eligible_cells: z.number().int().nonnegative(),
  partial_boundary_cells: z.number().int().nonnegative(),
  partial_cell_detections: z.number().int().nonnegative(),
  occupied_cell_fraction_convention_a: z.number().min(0).max(1).nullable(),
  occupied_cells_convention_a: z.number().int().nonnegative(),
}).passthrough();

const calendarSensorSchema = z.object({
  label: z.string(),
  available: z.boolean(),
  months: z.array(monthSchema),
}).passthrough();

const sensorIdSchema = z.enum(["MODIS_C61", "VIIRS_J1_C2"]);
const sensorRecordSchema = z.object({
  MODIS_C61: calendarSensorSchema,
  VIIRS_J1_C2: calendarSensorSchema,
}).passthrough();

const regionSchema = z.object({
  region_id: z.string(),
  name: z.string(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  supported_sensors: z.array(z.string()),
  supported_years: z.array(z.number().int()),
  grid_resolution_deg: z.number().positive(),
  notes: z.string(),
}).passthrough();

const configurationSchema = z.object({
  sensor: sensorIdSchema,
  grid_deg: z.number().positive(),
  baseline_start: z.number().int(),
  baseline_end: z.number().int(),
  elevated_quantile: z.number().min(0).max(1),
  grid_convention: z.string(),
}).passthrough();

const sensorSpecificSchema = z.object({
  n_configs: z.number().int().nonnegative(),
  n_evaluable: z.number().int().nonnegative(),
  n_elevated: z.number().int().nonnegative(),
  n_not_elevated: z.number().int().nonnegative(),
  label: z.string(),
}).passthrough();
const sensorSpecificRecordSchema = z.object({
  MODIS_C61: sensorSpecificSchema,
  VIIRS_J1_C2: sensorSpecificSchema,
}).passthrough();

const reliabilityPeriodSchema = z.object({
  period: z.string().regex(/^\d{4}-\d{2}$/),
  year: z.number().int(),
  month: z.number().int().min(1).max(12),
  stability_label: z.string(),
  n_configs_total: z.number().int().nonnegative(),
  n_elevated: z.number().int().nonnegative(),
  n_not_elevated: z.number().int().nonnegative(),
  n_insufficient: z.number().int().nonnegative(),
  n_evaluable: z.number().int().nonnegative(),
  min_evaluable_required: z.number().int().nonnegative(),
  evaluable_fraction: z.number().min(0).max(1),
  n_not_run: z.number().int().nonnegative(),
  cross_sensor_requirement_met: z.boolean(),
  sensors_lacking_evaluable_config: z.array(z.string()),
  sensor_specific: sensorSpecificRecordSchema,
  fixture_configs: z.number().int().nonnegative(),
}).passthrough();

export const regionsSchema = z.object({
  ...metadata,
  regions: z.array(regionSchema),
}).passthrough();

export const calendarSchema = z.object({
  ...metadata,
  region_id: z.string(),
  baseline_window: z.object({ start: z.number().int(), end: z.number().int() }),
  grid_resolution_deg: z.number().positive(),
  primary_grid_convention: z.string(),
  sensitivity_grid_convention: z.string(),
  metric_definitions: z.record(z.string(), z.unknown()),
  grid_cells: z.record(z.string(), z.unknown()),
  area_caveat: z.string(),
  missing_data_note: z.string(),
  sensors: sensorRecordSchema,
}).passthrough();

export const sensorsSchema = z.object({
  ...metadata,
  region_id: z.string(),
  sensor_metadata: z.record(sensorIdSchema, z.object({
    label: z.string(),
    available: z.boolean(),
  }).passthrough()),
  overlap_diagnostics: z.object({
    n_overlap_months: z.number().int().nonnegative(),
    harmonization_supported: z.boolean(),
    harmonization_note: z.string(),
    detail: z.array(z.object({
      period: z.string(),
      modis_ocf: z.number().nullable(),
      viirs_ocf: z.number().nullable(),
      ratio_viirs_modis: z.number().nullable().optional(),
      abs_difference: z.number().nullable().optional(),
    }).passthrough()),
    limitations: z.array(z.string()),
  }).passthrough(),
}).passthrough();

export const reliabilitySchema = z.object({
  ...metadata,
  region_id: z.string(),
  stability_labels: z.record(z.string(), z.string()),
  sensor_specific_labels: z.record(z.string(), z.string()),
  cross_sensor_rule: z.object({
    min_evaluable_configs: z.number().int().nonnegative(),
    required_sensors: z.array(sensorIdSchema),
    min_evaluable_per_sensor: z.number().int().nonnegative(),
  }).passthrough(),
  configurations: z.record(z.string(), configurationSchema),
  config_registry_version: z.number().int().positive(),
  config_registry_history: z.record(z.string(), z.array(z.string())),
  per_period: z.array(reliabilityPeriodSchema),
  limitations: z.array(z.string()),
  min_evaluable_configs: z.number().int().nonnegative(),
}).passthrough();

export const methodologySchema = z.object({
  ...metadata,
  region: z.object({
    id: z.string(),
    name: z.string(),
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
    source: z.string(),
  }).passthrough(),
  data_sources: z.array(z.object({
    sensor: z.string(),
    product: z.string(),
    provider: z.string(),
    url: z.string().url(),
    temporal_coverage: z.string(),
    access_method: z.string(),
    product_versions: z.array(z.string()),
    source_types: z.array(z.enum(["archive", "nrt"])),
    source_versions_by_type: z.record(z.string(), z.array(z.string())),
    provenance_note: z.string(),
  }).passthrough()),
  processing_steps: z.array(z.string()),
  index_definition: z.object({
    name: z.string(),
    formula: z.string(),
    unit: z.string(),
    denominator: z.string(),
    not_area_weighted: z.boolean(),
    interpretation_caveat: z.string(),
    limitations: z.array(z.string()),
  }).passthrough(),
  baseline_window: z.object({
    start: z.number().int(),
    end: z.number().int(),
    note: z.string(),
  }).passthrough(),
  geographic_support: z.object({
    primary_convention: z.string(),
    sensitivity_convention: z.string(),
    metric_definitions: z.record(z.string(), z.unknown()),
    decision: z.string(),
    note: z.string(),
    cell_counts: z.array(z.object({
      convention: z.string(),
      resolution_deg: z.number(),
      eligible_cells: z.number(),
      fully_interior_cells: z.number(),
      partial_boundary_cells: z.number(),
    }).passthrough()),
    by_resolution: z.array(z.record(z.string(), z.unknown())),
  }).passthrough(),
  reliability_min_evaluable_configs: z.number().int().nonnegative(),
  reliability_cross_sensor_rule: z.object({
    required_sensors: z.array(sensorIdSchema),
    min_evaluable_per_sensor: z.number().int().nonnegative(),
  }).passthrough(),
  reliability_configurations: z.record(z.string(), configurationSchema),
  reliability_config_registry_version: z.number().int().positive(),
  scientific_guardrails: z.array(z.string()),
}).passthrough();

export type RegionsData = z.infer<typeof regionsSchema>;
export type CalendarData = z.infer<typeof calendarSchema>;
export type SensorsData = z.infer<typeof sensorsSchema>;
export type ReliabilityData = z.infer<typeof reliabilitySchema>;
export type MethodologyData = z.infer<typeof methodologySchema>;

export interface FireChronicleData {
  regions: RegionsData;
  calendar: CalendarData;
  sensors: SensorsData;
  reliability: ReliabilityData;
  methodology: MethodologyData;
}

// Optional sixth file: historical-to-recent activity (primary configuration only).
const recentRecordSchema = z.object({
  sensor: z.enum(["MODIS_C61", "VIIRS_J1_C2"]),
  period: z.string().regex(/^\d{4}-\d{2}$/),
  year: z.number().int(),
  month: z.number().int().min(1).max(12),
  period_role: z.enum(["holdout", "recent"]),
  source_type: z.enum(["archive", "nrt", "archive+nrt"]).nullable(),
  has_data: z.boolean(),
  coverage_note: z.string().nullable(),
  occupied_cell_fraction: z.number().min(0).max(1).nullable(),
  baseline_median: z.number().nullable(),
  elevated_threshold: z.number().nullable(),
  anomaly: z.number().nullable(),
  elevated: z.boolean().nullable(),
  historical_rank: z.number().int().min(1).nullable(),
  n_historical_values: z.number().int().nonnegative(),
  n_historical_values_below: z.number().int().nonnegative().nullable(),
  n_historical_values_tied: z.number().int().nonnegative().nullable(),
}).refine((r) => r.has_data || (r.occupied_cell_fraction === null && r.elevated === null && r.historical_rank === null), {
  message: "months without data must have null metrics",
});

const recentReferenceSchema = z.object({
  month: z.number().int().min(1).max(12),
  baseline_median: z.number().nullable(),
  elevated_threshold: z.number().nullable(),
  historical_values: z.record(z.string(), z.number().nullable()),
});

export const recentActivitySchema = z.object({
  recent_activity_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  based_on_contract_version: z.string(),
  generated_at: z.string().datetime({ offset: true }),
  is_fixture: z.boolean(),
  configuration: z.object({
    grid_convention: z.string(),
    grid_resolution_deg: z.number(),
    elevated_quantile: z.number(),
    historical_rank_definition: z.string(),
  }).passthrough(),
  periods: z.object({
    reference: z.object({ start: z.number().int(), end: z.number().int() }).passthrough(),
    holdout: z.object({ year: z.number().int() }),
    recent: z.object({ year: z.number().int() }),
  }),
  sources: z.array(z.object({
    sensor: z.string(), source_type: z.string(), filename: z.string(), sha256: z.string().regex(/^[0-9a-f]{64}$/),
    date_min: z.string(), date_max: z.string(),
  }).passthrough()),
  sensors: z.object({
    MODIS_C61: z.object({ label: z.string(), reference: z.array(recentReferenceSchema).length(12), records: z.array(recentRecordSchema) }).passthrough(),
    VIIRS_J1_C2: z.object({ label: z.string(), reference: z.array(recentReferenceSchema).length(12), records: z.array(recentRecordSchema) }).passthrough(),
  }),
  limitations: z.array(z.string()),
}).passthrough();

export type RecentActivityData = z.infer<typeof recentActivitySchema>;
export type RecentRecord = RecentActivityData["sensors"]["MODIS_C61"]["records"][number];

// Optional seventh file: Stage 6E harmonization evaluation (leave-one-year-out, diagnostic only).
const methodScoresSchema = z.object({
  A_seasonal: z.number().nonnegative(),
  B_global: z.number().nonnegative(),
  C_climatology: z.number().nonnegative(),
});

export const harmonizationSchema = z.object({
  harmonization_evaluation_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  status: z.literal("diagnostic"),
  source: z.object({
    file: z.string(),
    sha256_lf_normalized: z.string().regex(/^[0-9a-f]{64}$/),
    input_calendar_sha256_lf_normalized: z.string().regex(/^[0-9a-f]{64}$/),
  }),
  definition: z.object({
    predictor: z.string(),
    target: z.string(),
    validation: z.string(),
    years: z.array(z.number().int()).min(2),
    metric: z.string(),
  }),
  methods: z.object({ A_seasonal: z.string(), B_global: z.string(), C_climatology: z.string() }),
  mae: methodScoresSchema,
  mae_by_year: z.record(z.string(), methodScoresSchema),
  folds_A_better_than_B: z.number().int().nonnegative(),
  folds_A_better_than_C: z.number().int().nonnegative(),
  n_evaluated: z.number().int().positive(),
  conclusion: z.string(),
  decision: z.string(),
});

export type HarmonizationData = z.infer<typeof harmonizationSchema>;

// Optional eighth file: per-cell monthly detection counts for the Overview map.
const cellSensorSchema = z.object({
  source_coverage: z.record(z.string(), z.tuple([z.string(), z.string()])),
  periods: z.record(z.string().regex(/^\d{4}-\d{2}$/), z.array(z.tuple([z.number().int().nonnegative(), z.number().int().positive()]))),
});

export const cellActivitySchema = z.object({
  cell_activity_version: z.string().regex(/^\d+\.\d+\.\d+$/),
  is_fixture: z.boolean(),
  grid: z.object({
    convention: z.string(),
    resolution_deg: z.number().positive(),
    bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
    cells: z.array(z.tuple([z.number(), z.number()])).min(1),
  }),
  reproduction_check: z.record(z.string(), z.object({ passed: z.literal(true) }).passthrough()),
  sensors: z.object({ MODIS_C61: cellSensorSchema, VIIRS_J1_C2: cellSensorSchema }),
}).passthrough().refine(
  (data) => Object.values(data.sensors).every((sensor) =>
    Object.values(sensor.periods).every((cells) => cells.every(([index]) => index < data.grid.cells.length))),
  { message: "cell index outside the grid" },
);

export type CellActivityData = z.infer<typeof cellActivitySchema>;

export const SENSOR_IDS = ["MODIS_C61", "VIIRS_J1_C2"] as const;
export type SensorId = (typeof SENSOR_IDS)[number];
export type CalendarMonth = CalendarData["sensors"][SensorId]["months"][number];
export type ReliabilityPeriod = ReliabilityData["per_period"][number];
