import { afterEach, describe, expect, it, vi } from "vitest";
import { AOI_LABEL, downloadJson, formatAnomalyLabel, formatConfigName, IN_SAMPLE_NOTE, MODIS_RECORD_NOTE, RELIABILITY_NOTE, SCOPE_NOTE, SPEARMAN_NOTE, toCsv, TYPE_FIELD_NOTE } from "./shared";

describe("configuration names", () => {
  it("keeps official MODIS and VIIRS capitalization", () => {
    expect(formatConfigName("viirs_primary_grid")).toBe("VIIRS Primary Grid");
    expect(formatConfigName("modis_coarse_grid")).toBe("MODIS Coarse Grid");
    expect(formatConfigName("modis_strict_threshold")).toBe("MODIS Strict Threshold");
    expect(formatConfigName("primary")).toBe("Primary");
  });
});

describe("scientific wording", () => {
  it("never shows a single-configuration result as cross-configuration agreement", () => {
    expect(formatAnomalyLabel("consistently_elevated")).toBe("elevated (single configuration)");
    expect(formatAnomalyLabel("not_elevated")).toBe("not elevated");
    expect(formatAnomalyLabel("insufficient_evidence")).toBe("insufficient evidence");
  });

  it("states that classifications are in-sample and not holdout-validated", () => {
    expect(IN_SAMPLE_NOTE).toMatch(/descriptive and in-sample/);
    expect(IN_SAMPLE_NOTE).toMatch(/2019–2024/);
    expect(IN_SAMPLE_NOTE).toMatch(/high within-month historical rank, not a validated prediction/);
    expect(IN_SAMPLE_NOTE).toMatch(/No independent holdout validation/);
  });

  it("discloses the Stage 6B audit findings with the audited numbers", () => {
    expect(MODIS_RECORD_NOTE).toMatch(/2019–2022 are MODIS Collection 6 \(version 6\.03\); from January 2023 they are Collection 6\.1/);
    expect(MODIS_RECORD_NOTE).toMatch(/10:35 to 08:39 local time for Terra/);
    expect(MODIS_RECORD_NOTE).toMatch(/13:41 to 15:43 for Aqua/);
    expect(MODIS_RECORD_NOTE).toMatch(/not a ground truth or a replacement for MODIS/);
    expect(TYPE_FIELD_NOTE).toMatch(/does not filter the FIRMS archive `type` field/);
    expect(TYPE_FIELD_NOTE).toMatch(/3\.1% of retained 2019–2024 VIIRS detections/);
    expect(TYPE_FIELD_NOTE).toMatch(/at most 2\.8 percentage points/);
    expect(SPEARMAN_NOTE).toMatch(/assumes independent observations/);
    expect(SPEARMAN_NOTE).toMatch(/should not be read as though all 72 months were independent/);
    expect(RELIABILITY_NOTE).toMatch(/not independent datasets/);
    expect(RELIABILITY_NOTE).toMatch(/zero changes by construction/);
    expect(RELIABILITY_NOTE).toMatch(/changes 3 of 72 classifications, none of which alters a reported stability label/);
    expect(SCOPE_NOTE).toMatch(/sensor-aware historical fire-activity and reliability pilot/);
    expect(SCOPE_NOTE).toMatch(/Historical window 2019–2024/);
    expect(SCOPE_NOTE).toMatch(/not calibrated or fused into an equivalent series/);
    expect(SCOPE_NOTE).toMatch(/does not span 20\+ years/);
  });

  it("names the study area conservatively", () => {
    expect(AOI_LABEL).toBe("South Sumatra-region pilot AOI");
  });
});

describe("data exports", () => {
  const originalCreateObjectURL = URL.createObjectURL;
  const originalRevokeObjectURL = URL.revokeObjectURL;

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalCreateObjectURL) {
      Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectURL });
    } else {
      Reflect.deleteProperty(URL, "createObjectURL");
    }
    if (originalRevokeObjectURL) {
      Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectURL });
    } else {
      Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("creates downloadable JSON and CSV files with their requested names", () => {
    const createObjectURL = vi.fn((_blob: Blob) => "blob:firechronicle");
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    const downloaded: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloaded.push(this.download);
    });

    downloadJson("calendar.json", { contract_version: "1.2.0" });
    toCsv("calendar.csv", [{ sensor: "MODIS_C61", value: 0.1 }]);

    expect(downloaded).toEqual(["calendar.json", "calendar.csv"]);
    expect(createObjectURL).toHaveBeenCalledTimes(2);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(createObjectURL.mock.calls[1][0]).toBeInstanceOf(Blob);
    expect(document.querySelector("a[download]")).toBeNull();
  });
});
