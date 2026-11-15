import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { calendarSchema, cellActivitySchema, SENSOR_IDS } from "../data/contracts";
import { loadCellActivity } from "../data/loadData";
import { aggregateCells, availableYears, INTENSITY_COLORS, intensityClass, legendEntries } from "./cellActivity";

const read = (name: string) => JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", name), "utf8"));
const raw = read("cell_activity.json");
const cells = cellActivitySchema.parse(raw);
const calendar = calendarSchema.parse(read("calendar.json"));

describe("cell_activity.json", () => {
  it("uses the 288-cell Convention B grid and has no point coordinates", () => {
    expect(cells.grid.convention).toBe("B");
    expect(cells.grid.cells).toHaveLength(288);
    expect(JSON.stringify(raw)).not.toMatch(/"latitude"|"longitude"|acq_time/);
  });

  it("reproduces detection_count and occupied_cells of calendar.json for every 2019–2024 month", () => {
    for (const sensor of SENSOR_IDS) {
      for (const month of calendar.sensors[sensor].months) {
        const perCell = cells.sensors[sensor].periods[month.period] ?? [];
        expect(perCell.reduce((total, [, n]) => total + n, 0)).toBe(month.detection_count);
        expect(perCell.length).toBe(month.occupied_cells);
      }
    }
  });

  it("sums the selection correctly and keeps the sensors separate", () => {
    const baseline = { years: [2019, 2020, 2021, 2022, 2023, 2024], month: null };
    const modis = aggregateCells(cells, "MODIS_C61", baseline);
    const viirs = aggregateCells(cells, "VIIRS_J1_C2", baseline);
    expect([...modis.values()].reduce((a, b) => a + b, 0)).toBe(31781);
    expect([...viirs.values()].reduce((a, b) => a + b, 0)).toBe(148913);
    const september2019 = aggregateCells(cells, "VIIRS_J1_C2", { years: [2019], month: 9 });
    const record = calendar.sensors.VIIRS_J1_C2.months.find((m) => m.period === "2019-09")!;
    expect(september2019.size).toBe(record.occupied_cells);
    expect(availableYears(cells)).toEqual([2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]);
  });

  it("never repeats a legend value, and every legend colour is a class that can occur", () => {
    for (const max of [1, 2, 4, 7, 50, 6722]) {
      const entries = legendEntries(max);
      const values = entries.map((entry) => entry.from);
      expect(new Set(values).size).toBe(values.length);
      for (const { color, from } of entries) {
        expect(INTENSITY_COLORS[intensityClass(from, max)]).toBe(color);
      }
    }
  });

  it("maps counts to ordered intensity classes", () => {
    expect(intensityClass(1, 1000)).toBe(0);
    expect(intensityClass(1000, 1000)).toBe(4);
    expect(intensityClass(250, 1000)).toBeLessThan(intensityClass(800, 1000));
  });

  it("is optional: the loader returns null when missing, invalid or fixture-derived", async () => {
    expect(await loadCellActivity((async () => new Response("", { status: 404 })) as typeof fetch)).toBeNull();
    expect(await loadCellActivity((async () => new Response("{}", { status: 200 })) as typeof fetch)).toBeNull();
    expect(await loadCellActivity((async () => new Response(JSON.stringify({ ...raw, is_fixture: true }), { status: 200 })) as typeof fetch)).toBeNull();
    expect(await loadCellActivity((async () => new Response(JSON.stringify(raw), { status: 200 })) as typeof fetch)).not.toBeNull();
  });
});
