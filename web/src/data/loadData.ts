import {
  calendarSchema,
  cellActivitySchema,
  harmonizationSchema,
  methodologySchema,
  recentActivitySchema,
  regionsSchema,
  reliabilitySchema,
  sensorsSchema,
  type CellActivityData,
  type FireChronicleData,
  type HarmonizationData,
  type RecentActivityData,
} from "./contracts";

const DATA_FILES = {
  regions: ["regions.json", regionsSchema],
  calendar: ["calendar.json", calendarSchema],
  sensors: ["sensors.json", sensorsSchema],
  reliability: ["reliability.json", reliabilitySchema],
  methodology: ["methodology.json", methodologySchema],
} as const;

export class DataLoadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DataLoadError";
  }
}

export async function loadFireChronicleData(
  fetcher: typeof fetch = fetch,
): Promise<FireChronicleData> {
  const entries = await Promise.all(
    Object.entries(DATA_FILES).map(async ([name, [filename, schema]]) => {
      let response: Response;
      try {
        response = await fetcher(`/data/${filename}`);
      } catch (error) {
        throw new DataLoadError(`Could not load ${filename}: ${String(error)}`);
      }

      if (!response.ok) {
        throw new DataLoadError(`${filename} returned HTTP ${response.status}`);
      }

      let json: unknown;
      try {
        json = await response.json();
      } catch (error) {
        throw new DataLoadError(`${filename} is not valid JSON: ${String(error)}`);
      }

      const parsed = schema.safeParse(json);
      if (!parsed.success) {
        const issue = parsed.error.issues[0];
        throw new DataLoadError(
          `${filename} does not match the data contract at ${issue.path.join(".") || "root"}: ${issue.message}`,
        );
      }
      return [name, parsed.data] as const;
    }),
  );

  const data = Object.fromEntries(entries) as unknown as FireChronicleData;
  const versions = new Set(Object.values(data).map((file) => file.contract_version));
  if (versions.size !== 1) {
    throw new DataLoadError(`Data contract versions do not match: ${[...versions].join(", ")}`);
  }
  return data;
}

/**
 * Load the optional recent-activity file. Never throws: returns null when the file
 * is absent, unreadable, fixture-derived or does not match its schema, so the rest
 * of the application keeps working.
 */
export async function loadRecentActivity(
  fetcher: typeof fetch = fetch,
): Promise<RecentActivityData | null> {
  try {
    const response = await fetcher("/data/recent_activity.json");
    if (!response.ok) return null;
    const parsed = recentActivitySchema.safeParse(await response.json());
    if (!parsed.success || parsed.data.is_fixture) return null;
    return parsed.data;
  } catch {
    return null;
  }
}

/** Load the optional harmonization-evaluation file. Never throws; returns null when absent or invalid. */
export async function loadHarmonization(
  fetcher: typeof fetch = fetch,
): Promise<HarmonizationData | null> {
  try {
    const response = await fetcher("/data/harmonization.json");
    if (!response.ok) return null;
    const parsed = harmonizationSchema.safeParse(await response.json());
    return parsed.success ? parsed.data : null;
  } catch {
    return null;
  }
}

/** Load the optional per-cell map file. Never throws; returns null when absent, invalid or fixture-derived. */
export async function loadCellActivity(
  fetcher: typeof fetch = fetch,
): Promise<CellActivityData | null> {
  try {
    const response = await fetcher("/data/cell_activity.json");
    if (!response.ok) return null;
    const parsed = cellActivitySchema.safeParse(await response.json());
    return parsed.success && !parsed.data.is_fixture ? parsed.data : null;
  } catch {
    return null;
  }
}

export function hasFixtureData(data: FireChronicleData): boolean {
  return Object.values(data).some((file) => file.is_fixture);
}

export function fixtureWarnings(data: FireChronicleData): string[] {
  return Object.values(data)
    .filter((file) => file.is_fixture)
    .map((file) => file.fixture_warning)
    .filter((warning): warning is string => Boolean(warning));
}
