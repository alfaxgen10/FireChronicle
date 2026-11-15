import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import {
  calendarSchema,
  methodologySchema,
  regionsSchema,
  reliabilitySchema,
  sensorsSchema,
  type FireChronicleData,
} from "../data/contracts";
import OverviewPage from "./OverviewPage";

function readJson(filename: string): unknown {
  return JSON.parse(readFileSync(resolve(process.cwd(), "public", "data", filename), "utf8"));
}

const data: FireChronicleData = {
  regions: regionsSchema.parse(readJson("regions.json")),
  calendar: calendarSchema.parse(readJson("calendar.json")),
  sensors: sensorsSchema.parse(readJson("sensors.json")),
  reliability: reliabilitySchema.parse(readJson("reliability.json")),
  methodology: methodologySchema.parse(readJson("methodology.json")),
};

function renderOverview() {
  return render(
    <MemoryRouter>
      <OverviewPage data={data} />
    </MemoryRouter>,
  );
}

describe("Overview page", () => {
  it("provides the project purpose and routes to the dashboard", () => {
    renderOverview();

    expect(screen.getByRole("heading", { name: /FireChronicle/ })).toBeVisible();
    expect(screen.getByRole("link", { name: /Explore the analysis/ })).toHaveAttribute("href", "/explore");

    const navigation = screen.getByRole("region", { name: "The observation workspace" });
    const destinations = Array.from(navigation.querySelectorAll("a[href]"))
      .map((link) => link.getAttribute("href"));
    expect(destinations).toEqual(["/explore", "/calendar", "/reliability", "/methodology"]);
  });

  it("derives the displayed findings from the production exports", () => {
    const { container } = renderOverview();

    const findings = Array.from(container.querySelectorAll(".overview-finding"));
    expect(findings[0].textContent).toContain("72 months");
    expect(findings[1].textContent).toContain("19.5% vs 42.6%");
    expect(findings[2].textContent).toContain("26 of 72");
    expect(findings[1].textContent).toMatch(/not equivalent fire counts or a calibration factor/i);
  });

  it("states the key scientific limitations", () => {
    const { container } = renderOverview();

    const heading = Array.from(container.querySelectorAll("h2"))
      .find((element) => element.textContent === "Scientific limitations");
    const limitations = heading?.closest("section")?.textContent ?? "";
    expect(limitations).toMatch(/not counts of individual fires, fire perimeters, or burned area/i);
    expect(limitations).toMatch(/Cross-sensor harmonization has not been scientifically established or applied/i);
    expect(limitations).toMatch(/not the probability that a result is correct/i);
    expect(limitations).toMatch(/descriptive and in-sample/i);
    expect(limitations).toMatch(/No independent holdout validation/i);
    expect(limitations).toMatch(/not been verified against provincial boundaries/i);
    expect(limitations).toMatch(/partly inside the box but counts as full cells/i);
    expect(limitations).toMatch(/Collection 6 \(version 6\.03\)/);
    expect(limitations).toMatch(/does not filter the FIRMS archive `type` field/);
    expect(limitations).toMatch(/Spearman correlation p-value .* assumes independent observations/);
    expect(limitations).toMatch(/zero changes by construction/);
    expect(limitations).toMatch(/does not span 20\+ years/);
  });
});

describe("Overview evidence chart", () => {
  it("exposes an accessible title and description that state its limits", () => {
    const { container } = renderOverview();

    const svg = container.querySelector("svg.overview-chart");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("role", "img");
    const ids = (svg?.getAttribute("aria-labelledby") ?? "").split(/\s+/);
    expect(ids).toEqual(["overview-chart-title", "overview-chart-desc"]);
    const [title, description] = ids.map((id) => container.querySelector(`#${id}`)?.textContent ?? "");
    expect(title).toMatch(/occupied-cell fraction by sensor/i);
    expect(description).toMatch(/72 months with quality-filtered detections from both sensors/);
    expect(description).toMatch(/2019-01 to 2024-12/);
    expect(description).toMatch(/uncalibrated/);
    expect(description).toMatch(/MODIS is drawn as a dashed line and VIIRS as a solid line/);
  });

  it("plots 72 points per sensor on a 0-45-90% axis without relying on colour alone", () => {
    const { container } = renderOverview();

    for (const sensor of ["modis", "viirs"]) {
      const path = container.querySelector(`path.overview-chart-line.${sensor}`)?.getAttribute("d") ?? "";
      expect(path.match(/[ML]/g)).toHaveLength(72);
    }
    const labels = Array.from(container.querySelectorAll(".overview-chart-label")).map((node) => node.textContent);
    expect(labels).toEqual(expect.arrayContaining(["0%", "45%", "90%", "2019", "2024"]));

    const legend = container.querySelector(".overview-legend")?.textContent ?? "";
    expect(legend).toMatch(/MODIS \(dashed\)/);
    expect(legend).toMatch(/VIIRS \(solid\)/);

    const css = readFileSync(resolve(process.cwd(), "src", "styles.css"), "utf8");
    expect(css).toMatch(/\.overview-chart-line\.modis\s*\{[^}]*stroke-dasharray/);
  });

  it("defines the index, the 288-cell denominator and the quality filter near the chart", () => {
    const { container } = renderOverview();

    const caption = container.querySelector(".overview-figure figcaption")?.textContent ?? "";
    expect(caption).toMatch(/share of the 288 eligible 0\.25° grid cells/);
    expect(caption).toMatch(/quality-filtered detection/);
    expect(caption).toMatch(/not calibrated to each other and are not fire counts or burned area/);
  });

  it("reports the verified summary values and no longer says 'paired months'", () => {
    const { container } = renderOverview();

    const text = container.textContent ?? "";
    expect(text).toContain("19.5% vs 42.6%");
    expect(text).toContain("26 of 72");
    expect(text).toMatch(/across the 72 months with detections from both sensors/);
    expect(text).not.toMatch(/paired months/i);
    expect(text).toMatch(/would not establish zero fire activity/);
  });
});

describe("Overview harmonization limitation", () => {
  function renderWithHarmonization(supported: boolean) {
    const modified = structuredClone(data);
    modified.sensors.overlap_diagnostics.harmonization_supported = supported;
    return render(
      <MemoryRouter>
        <OverviewPage data={modified} />
      </MemoryRouter>,
    );
  }

  it("shows the existing limitation while harmonization is not supported", () => {
    expect(data.sensors.overlap_diagnostics.harmonization_supported).toBe(false);
    const { container } = renderWithHarmonization(false);

    const limitations = container.querySelector(".overview-limits")?.textContent ?? "";
    expect(limitations).toContain(
      "Cross-sensor harmonization has not been scientifically established or applied; MODIS and VIIRS series remain separate.",
    );
  });

  it("never claims harmonization or calibration was applied when the flag is true", () => {
    const { container } = renderWithHarmonization(true);

    const limitations = container.querySelector(".overview-limits")?.textContent ?? "";
    expect(limitations).toMatch(/flags harmonization as supported, but this page applies none/);
    expect(limitations).toMatch(/remain separate and uncalibrated/);
    expect(limitations).not.toMatch(/has not been scientifically established/);
    expect(limitations).not.toMatch(/harmonized|calibrated to/i);
  });
});