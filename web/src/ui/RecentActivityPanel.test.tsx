import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { recentActivitySchema } from "../data/contracts";
import { loadRecentActivity } from "../data/loadData";
import RecentActivityPanel from "./RecentActivityPanel";

const raw = JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", "recent_activity.json"), "utf8"));
const recent = recentActivitySchema.parse(raw);

function elevatedMonths(sensor: "MODIS_C61" | "VIIRS_J1_C2", year: number) {
  return recent.sensors[sensor].records.filter((r) => r.year === year && r.elevated === true).map((r) => r.month);
}

describe("recent_activity.json contract", () => {
  it("parses and keeps sensors separate with explicit missing months", () => {
    expect(recent.is_fixture).toBe(false);
    expect(recent.configuration.grid_convention).toBe("B");
    for (const sensor of ["MODIS_C61", "VIIRS_J1_C2"] as const) {
      const records = recent.sensors[sensor].records;
      expect(records).toHaveLength(24);
      expect(new Set(records.map((r) => r.sensor))).toEqual(new Set([sensor]));
      for (const period of ["2026-11", "2026-12"]) {
        const r = records.find((x) => x.period === period)!;
        expect(r.has_data).toBe(false);
        expect(r.occupied_cell_fraction).toBeNull();
        expect(r.elevated).toBeNull();
      }
    }
  });

  it("matches the corrected elevated-month lists", () => {
    expect(elevatedMonths("MODIS_C61", 2025)).toEqual([2, 6, 7]);
    expect(elevatedMonths("VIIRS_J1_C2", 2025)).toEqual([5, 6]);
    expect(elevatedMonths("MODIS_C61", 2026)).toEqual([1, 2, 3, 5, 6, 7, 8, 9, 10]);
    expect(elevatedMonths("VIIRS_J1_C2", 2026)).toEqual([1, 3, 6, 7, 8, 9, 10]);
  });

  it("rejects a month without data that carries metrics", () => {
    const broken = structuredClone(raw);
    const r = broken.sensors.MODIS_C61.records.find((x: { period: string }) => x.period === "2026-11");
    r.occupied_cell_fraction = 0;
    expect(recentActivitySchema.safeParse(broken).success).toBe(false);
  });
});

describe("optional loader", () => {
  it("returns null when the file is missing, invalid or fixture-derived", async () => {
    const notFound = async () => new Response("", { status: 404 });
    const invalid = async () => new Response(JSON.stringify({ hello: "world" }), { status: 200 });
    const fixture = async () => new Response(JSON.stringify({ ...raw, is_fixture: true }), { status: 200 });
    const failing = async () => { throw new Error("offline"); };
    expect(await loadRecentActivity(notFound as typeof fetch)).toBeNull();
    expect(await loadRecentActivity(invalid as typeof fetch)).toBeNull();
    expect(await loadRecentActivity(fixture as typeof fetch)).toBeNull();
    expect(await loadRecentActivity(failing as typeof fetch)).toBeNull();
    const ok = async () => new Response(JSON.stringify(raw), { status: 200 });
    expect(await loadRecentActivity(ok as typeof fetch)).not.toBeNull();
  });
});

describe("RecentActivityPanel", () => {
  it("shows reference, holdout and recent rows with missing months, NRT and limitations (VIIRS)", () => {
    const { container } = render(<RecentActivityPanel recent={recent} sensor="VIIRS_J1_C2" />);
    const rowHeaders = screen.getAllByRole("rowheader").map((cell) => cell.textContent ?? "");
    expect(rowHeaders).toHaveLength(4);
    expect(rowHeaders[0]).toMatch(/^Reference median 2019–2024/);
    expect(rowHeaders[1]).toMatch(/^Elevated threshold \(q75 of 6 years\)/);
    expect(rowHeaders[2]).toMatch(/^2025 holdout/);
    expect(rowHeaders[3]).toMatch(/^2026 recent/);
    expect(screen.getByText("2 of 12 elevated")).toBeVisible();
    expect(screen.getByText("7 of 10 elevated")).toBeVisible();
    expect(screen.getAllByText("Missing")).toHaveLength(2);
    expect(container.textContent).toMatch(/NRT/);
    const text = container.textContent ?? "";
    expect(text).toMatch(/only 6 historical values/);
    expect(text).toMatch(/not a statistical test, forecast or calibrated\s+cross-sensor fusion/);
    expect(text).toMatch(/does not show that the number of fires, burned area or damage increased/);
    expect(text).toMatch(/missing months are not zero activity/i);
  });

  it("keeps missing months and the full Jan–Dec range discoverable without scrolling", () => {
    const { container } = render(<RecentActivityPanel recent={recent} sensor="VIIRS_J1_C2" />);
    const rowHeaders = Array.from(container.querySelectorAll("th[scope='row']")).map((cell) => cell.textContent ?? "");
    expect(rowHeaders[2]).not.toMatch(/Missing/);              // 2025: all 12 months have data
    expect(rowHeaders[3]).toMatch(/Missing: Nov, Dec/);         // 2026: Nov and Dec not in downloaded files
    expect(container.querySelectorAll("thead th")).toHaveLength(13); // Period + 12 months
    // jsdom has no ResizeObserver, so the cue falls back to visible.
    expect(container.querySelector(".recent-scroll-cue")?.textContent).toMatch(/Scroll sideways to see all 12 months \(Jan–Dec\)/);
    expect(container.textContent).toMatch(/a month can be elevated while one or two\s+historical years were still higher/);
  });

  it("shows the MODIS record caveat only for MODIS and the type-field note for both sensors", () => {
    const modis = render(<RecentActivityPanel recent={recent} sensor="MODIS_C61" />);
    expect(modis.container.textContent).toMatch(/MODIS caveat:.*Collection 6 \(version 6\.03\).*10:35 to 08:39/);
    expect(modis.container.textContent).toMatch(/does not filter the FIRMS archive `type` field/);
    modis.unmount();
    const viirs = render(<RecentActivityPanel recent={recent} sensor="VIIRS_J1_C2" />);
    expect(viirs.container.textContent).not.toMatch(/MODIS caveat:/);
    expect(viirs.container.textContent).toMatch(/VIIRS note:.*not a ground truth or an equivalent replacement for MODIS/);
    expect(viirs.container.textContent).toMatch(/does not filter the FIRMS archive `type` field/);
    viirs.unmount();
  });

  it("uses the MODIS record when MODIS is selected, with ties and threshold meaning explained", () => {
    const { container } = render(<RecentActivityPanel recent={recent} sensor="MODIS_C61" />);
    expect(screen.getByText("3 of 12 elevated")).toBeVisible();
    expect(screen.getByText("9 of 10 elevated")).toBeVisible();
    const text = container.textContent ?? "";
    // MODIS 2025-04, 2026-02 and 2026-04 equal a historical value (same occupied-cell count).
    expect((text.match(/\(tied\)/g) ?? []).length).toBe(3);
    expect(text).toMatch(/ties \(equal values, compared at 6 decimals\) share the higher rank/);
    expect(text).toMatch(/“Elevated” = above this month's frozen threshold; “not elevated” = at or below it/);
    expect(text).toMatch(/“Missing” means\s+no value is reported/);
  });
});
