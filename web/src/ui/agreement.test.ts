import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import {
  calendarSchema, methodologySchema, recentActivitySchema, regionsSchema, reliabilitySchema, sensorsSchema,
  type FireChronicleData,
} from "../data/contracts";
import { buildAgreement, countStates } from "./agreement";
import AgreementCalendar from "./AgreementCalendar";

const read = (name: string) => JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", name), "utf8"));
const data: FireChronicleData = {
  regions: regionsSchema.parse(read("regions.json")),
  calendar: calendarSchema.parse(read("calendar.json")),
  sensors: sensorsSchema.parse(read("sensors.json")),
  reliability: reliabilitySchema.parse(read("reliability.json")),
  methodology: methodologySchema.parse(read("methodology.json")),
};
const recent = recentActivitySchema.parse(read("recent_activity.json"));
const months = (cells: ReturnType<typeof buildAgreement>, year: number, state: string) =>
  cells.filter((c) => c.year === year && c.state === state).map((c) => c.month);

describe("cross-sensor agreement", () => {
  const cells = buildAgreement(data, recent);

  it("covers 2019-01 to 2026-12 without recomputing any classification", () => {
    expect(cells).toHaveLength(96);
    for (const cell of cells.filter((c) => c.basis === "baseline")) {
      const m = data.calendar.sensors.MODIS_C61.months.find((x) => x.period === cell.period)!;
      const v = data.calendar.sensors.VIIRS_J1_C2.months.find((x) => x.period === cell.period)!;
      const expected = m.is_elevated && v.is_elevated ? "both" : m.is_elevated ? "modis_only" : v.is_elevated ? "viirs_only" : "neither";
      expect(cell.state).toBe(expected);
    }
  });

  it("matches the released 2025-2026 elevated lists", () => {
    expect(months(cells, 2025, "both")).toEqual([6]);
    expect(months(cells, 2026, "both")).toEqual([1, 3, 6, 7, 8, 9, 10]);
    expect(months(cells, 2026, "modis_only")).toEqual([2, 5]);
    expect(months(cells, 2026, "missing")).toEqual([11, 12]);
  });

  it("marks the 6 consistently elevated months, each elevated in both sensors", () => {
    const consistent = cells.filter((c) => c.stability === "consistently_elevated");
    expect(consistent).toHaveLength(6);
    for (const cell of consistent) expect(cell.state).toBe("both");
  });

  it("renders the summary, frozen-threshold rows and caveat without claiming calibration", () => {
    const counts = countStates(cells.filter((c) => c.basis === "baseline"));
    const { container } = render(createElement(AgreementCalendar, { data, recent }));
    const text = container.textContent ?? "";
    expect(text).toContain(`${counts.both}months elevated in both sensors`);
    expect(container.querySelectorAll(".agree-cell")).toHaveLength(96);
    expect(text).toMatch(/vs frozen/);
    expect(text).toMatch(/Agreement is not calibration/);
    expect(text).not.toMatch(/harmonized series|calibrated to/i);
  });
});
