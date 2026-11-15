# FireChronicle web application

The static React application consumes the five precomputed contracts in `public/data/`. It does not call a live NASA service or require a database.

## Local development

Requires Node.js `>=22.12.0 <23` (tested with 22.23.2 and npm 10.9.8).

```bash
npm ci
npm run dev
```

The app validates all five JSON exports at load time. Contract-shape errors and fetch failures are shown explicitly rather than replaced with default values.

## Quality checks

```bash
npm test
npm run build
```

## Production and Vercel

The production build is `dist/`. Deploy the `web/` directory as the Vercel project root; `vercel.json` directs client-side routes to the Vite entry point. The JSON files remain static assets under `/data/`.

## Data behavior

- Every export’s `is_fixture` and `fixture_warning` fields are respected. Fixture-derived results trigger a persistent, prominent warning.
- Explore draws the exported study-area bounding box only. No individual hotspot coordinates are present in these contracts, so no detection points are fabricated.
- Missing/null activity remains distinct from zero. MODIS and VIIRS are presented separately.
- Calendar Convention B values are primary; Convention A values are shown as sensitivity results.
- Reliability coverage and configuration registry are derived from the export rather than fixed frontend counts.
- CSV/JSON downloads contain the schema-validated, loaded data (contract checks only, not scientific validation).
- `recent_activity.json` is optional: if it is missing or fails its schema, the Historical-to-recent panel is hidden and the rest of the app works.
