import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { harmonizationSchema } from "../data/contracts";
import { loadHarmonization } from "../data/loadData";
import HarmonizationPanel from "./HarmonizationPanel";

const raw = JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", "harmonization.json"), "utf8"));
const harmonization = harmonizationSchema.parse(raw);
const stage6e = JSON.parse(readFileSync(resolve(process.cwd(), "..", "diagnostics", "stage6e", "results", "results.json"), "utf8"));

describe("harmonization.json", () => {
  it("copies the Stage 6E results without changing any value", () => {
    for (const key of ["A_seasonal", "B_global", "C_climatology"] as const) {
      expect(harmonization.mae[key]).toBe(stage6e.summary.mae[key]);
      for (const year of Object.keys(stage6e.summary.mae_by_year)) {
        expect(harmonization.mae_by_year[year][key]).toBe(stage6e.summary.mae_by_year[year][key]);
      }
    }
    expect(harmonization.folds_A_better_than_C).toBe(6);
    expect(harmonization.folds_A_better_than_B).toBe(3);
    expect(harmonization.status).toBe("diagnostic");
  });

  it("is optional: the loader returns null when it is missing or invalid", async () => {
    expect(await loadHarmonization((async () => new Response("", { status: 404 })) as typeof fetch)).toBeNull();
    expect(await loadHarmonization((async () => new Response("{}", { status: 200 })) as typeof fetch)).toBeNull();
    expect(await loadHarmonization((async () => new Response(JSON.stringify(raw), { status: 200 })) as typeof fetch)).not.toBeNull();
  });
});

describe("HarmonizationPanel", () => {
  it("shows the held-out errors, scores and the approved conclusion verbatim", () => {
    const { container } = render(<HarmonizationPanel harmonization={harmonization} />);
    const text = container.textContent ?? "";
    expect(text).toContain("6.6 pp");
    expect(text).toContain("7.3 pp");
    expect(text).toContain("9.7 pp");
    expect(text).toMatch(/6 of 6.*held-out years: monthly ratio beats the seasonal average/);
    expect(text).toMatch(/3 of 6.*held-out years: monthly ratio beats a single ratio/);
    expect(text).toContain(
      "The experiment evaluates a seasonal predictive relationship between VIIRS and MODIS occupied-cell fractions. Improved prediction does not establish sensor equivalence, measurement calibration, validated fusion or sensor-independent fire activity.",
    );
    expect(text).toMatch(/kept as separate records; no harmonized series is produced/);
  });
});
