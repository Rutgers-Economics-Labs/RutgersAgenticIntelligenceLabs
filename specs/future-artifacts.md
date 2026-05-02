# Future Artifacts

This document defines the artifact contract for the future RAIL platform.

## Principles

- filesystem is the source of truth
- the database may cache artifact metadata for speed
- artifact types should be explicit enough for the frontend to render intelligently
- artifact generation should support both static outputs and interactive outputs
- final artifacts should be evidence-backed, reproducible, and traceable to sources, assumptions, scripts, and verification results

## Artifact Types

The frontend should understand these first-class artifact types in V1:

- `report`
- `pdf`
- `chart`
- `dataset`
- `dashboard`
- `bundle`

## Type Definitions

### `report`

Human-readable report content, usually markdown-based.

Examples:

- `.md`
- rendered rich text summaries

### `pdf`

Portable document outputs.

Examples:

- papers
- exported reports
- slide-like documents

### `chart`

Visual plot outputs.

Examples:

- `.png`
- `.svg`
- chart-oriented JSON payloads

### `dataset`

Structured data outputs for analysis or download.

Examples:

- `.csv`
- `.json`
- `.parquet`

### `dashboard`

Interactive outputs intended for in-app rendering.

Supported dashboard styles in V1:

- JSON-configured dashboards
- HTML/CSS/JS dashboards

This means the frontend should support both:

- structured JSON dashboard configs rendered by native app components
- sandboxed or controlled HTML-based dashboards when explicitly produced as artifacts

### `bundle`

A folder or grouped set of related outputs.

Examples:

- report + charts + supporting datasets
- dashboard assets with companion files

## Artifact Locations

Artifacts should primarily live under `artifacts/`.

Topic-local outputs may exist under `topics/.../outputs/`, but user-facing deliverables should generally be promoted into `artifacts/`.

## Artifact Promotion States

Generated outputs should not become trusted deliverables merely because a worker wrote a nice-looking file.
RAIL should distinguish between exploratory outputs, verified artifacts, and final deliverables.

Recommended states:

- `exploratory`: useful during analysis, not intended for user trust yet
- `draft`: user-facing shape exists, but evidence or verification may still be incomplete
- `needs_evidence`: important claims, datasets, or charts lack source/evidence records
- `partially_verified`: some checks passed, but remaining checks or caveats are unresolved
- `verified`: lineage and deterministic verification checks passed
- `stale`: upstream assumptions, sources, scripts, or datasets changed after generation
- `blocked`: cannot be promoted until a blocker is resolved

Only `verified` artifacts should be presented as trusted outputs by default.
Draft and exploratory outputs may still be visible, but the UI should label them clearly.

## Artifact Lineage

Every final artifact should have lineage metadata.

Suggested metadata shape:

```json
{
  "artifact_path": "artifacts/report.md",
  "artifact_type": "report",
  "title": "NJ Housing Affordability Analysis",
  "promotion_state": "verified",
  "inputs": ["topics/housing/outputs/county_metrics.csv"],
  "scripts": ["topics/housing/scripts/analyze_affordability.py"],
  "sources": ["research_plan/state/sources.json#bls-laus", "research_plan/state/sources.json#acs-5-year"],
  "assumptions": ["research_plan/state/assumptions.json#years-2010-2024"],
  "claims": ["research_plan/state/claims.json#claim-001"],
  "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
  "generated_at": "2026-05-01T12:00:00Z"
}
```

Lineage metadata should be written into `research_plan/state/artifact_lineage.json` and may also be stored next to artifact bundles when useful.
If an upstream dependency changes, the artifact should be marked `stale` until rerun or revalidated.

## Artifact Indexing

Artifact indexing should be hybrid:

- filesystem is the source of truth
- the database stores a lightweight `artifact_index` cache for fast UI loading
- lineage and verification metadata come from repo-backed research state and may be cached for UI speed

The platform should be able to rebuild the index from the filesystem if needed.

## Rendering Rules

### Reports

Render inline when possible.

### PDFs

Render in an embedded viewer when possible, with download fallback.

### Charts

Render as images or structured chart components based on file type.

### Datasets

Render preview tables when practical, with download fallback.

### JSON Dashboards

Render through native dashboard components.

### HTML/CSS/JS Dashboards

Render through a controlled or sandboxed mechanism suitable for user-created frontend artifacts.

The spec should treat these as valid first-class artifacts, not as unsupported extras.

## Minimal Artifact Metadata

Suggested metadata fields for indexing:

- `path`
- `artifact_type`
- `title`
- `description`
- `promotion_state`
- `verification_status`
- `lineage_path`
- `commit_sha`
- `created_at`

## Claim Evidence For Reports

Reports and dashboards should avoid unsupported narrative claims.
Important claims should be mapped to evidence before artifact promotion.

Claim evidence records should capture:

- the claim text or stable claim identifier
- evidence paths such as source notes, generated datasets, scripts, SQL queries, charts, or verification outputs
- whether evidence is direct, derived, or contextual
- confidence/status label
- caveats or open questions

If a report contains claims that lack evidence records, the artifact should remain `needs_evidence` or `partially_verified`.

## Open Questions For Implementation

Implementation still needs to define:

- the sandboxing model for HTML/CSS/JS dashboards
- thumbnail generation strategy
- whether bundle manifests should be explicit files or inferred from directories
