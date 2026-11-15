import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  calendarSchema,
  methodologySchema,
  regionsSchema,
  reliabilitySchema,
  sensorsSchema,
  type FireChronicleData,
} from "./contracts";
import { FixtureNotice } from "../ui/shared";

function readJson(filename: string): unknown {
  return JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", filename), "utf8"));
}

const data = {
  regions: regionsSchema.parse(readJson("regions.json")),
  calendar: calendarSchema.parse(readJson("calendar.json")),
  sensors: sensorsSchema.parse(readJson("sensors.json")),
  reliability: reliabilitySchema.parse(readJson("reliability.json")),
  methodology: methodologySchema.parse(readJson("methodology.json")),
};

describe("exported frontend contracts", () => {
  it("validates all five committed data exports", () => {
    expect(new Set(Object.values(data).map((file) => file.contract_version)).size).toBe(1);
    expect(data.calendar.sensors.MODIS_C61.months).toHaveLength(72);
    expect(data.calendar.sensors.VIIRS_J1_C2.months).toHaveLength(72);
  });

  it("reads registry and per-period evaluability from the export", () => {
    expect(data.reliability.config_registry_version).toBe(2);
    expect(data.reliability.config_registry_history["2"]).toEqual(Object.keys(data.reliability.configurations));
    expect(data.reliability.per_period.every((period) => period.n_evaluable <= period.n_configs_total)).toBe(true);
    expect(data.methodology.reliability_config_registry_version).toBe(data.reliability.config_registry_version);
  });

  it("does not show a fixture warning for the real NASA exports", () => {
    render(<FixtureNotice data={data} />);
    expect(Object.values(data).every((file) => file.is_fixture === false)).toBe(true);
    expect(screen.queryByRole("alert", { name: /synthetic fixture data warning/i })).toBeNull();
  });

  it("keeps the fixture warning prominent when data are marked as synthetic", () => {
    const fixtureData: FireChronicleData = {
      ...data,
      calendar: {
        ...data.calendar,
        is_fixture: true,
        fixture_warning: "SYNTHETIC DATA — NOT A SCIENTIFIC OUTPUT",
      },
    };
    render(<FixtureNotice data={fixtureData} />);
    expect(screen.getByRole("alert", { name: /synthetic fixture data warning/i })).toBeVisible();
    expect(screen.getByText(/NOT NASA OBSERVATIONS/)).toBeVisible();
    expect(screen.getByText(/SYNTHETIC DATA/i)).toBeVisible();
  });

  it("rejects malformed geographic bounds instead of rendering them", () => {
    const region = readJson("regions.json") as { regions: Array<{ bbox: number[] }> };
    region.regions[0].bbox = [101.5, -4.9, 106.0];
    expect(regionsSchema.safeParse(region).success).toBe(false);
  });
});
