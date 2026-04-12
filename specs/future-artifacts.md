# Future Artifacts

This document defines the artifact contract for the future RAIL platform.

## Principles

- filesystem is the source of truth
- the database may cache artifact metadata for speed
- artifact types should be explicit enough for the frontend to render intelligently
- artifact generation should support both static outputs and interactive outputs

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

## Artifact Indexing

Artifact indexing should be hybrid:

- filesystem is the source of truth
- the database stores a lightweight `artifact_index` cache for fast UI loading

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
- `commit_sha`
- `created_at`

## Open Questions For Implementation

Implementation still needs to define:

- the sandboxing model for HTML/CSS/JS dashboards
- thumbnail generation strategy
- whether bundle manifests should be explicit files or inferred from directories

