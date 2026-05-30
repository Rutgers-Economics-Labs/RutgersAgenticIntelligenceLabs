# Current Plan

Project: Federal Research Grant Funding Analysis at Rutgers University

## Objective

Build a local, reproducible RAIL research project that summarizes public federal award records matching Rutgers University and clearly separates public-data findings from department-level claims that require internal Rutgers crosswalk data.

## Completed Scope

- Replaced placeholder source drafts with concrete USAspending.gov and NSF Awards API source configurations.
- Added a deterministic local build script that fetches or reuses cached public award data, normalizes it into a processed panel, and registers rail integrity state.
- Produced final artifacts under `artifacts/`: a research report, funding dashboard table, departmental-profile limitation note, and source quality note.
- Added a project verifier that fails on missing artifacts, missing lineage, missing claims, placeholder markers, or unsupported evidence links.

## Current Outputs

- `artifacts/federal_research_grants_report.md`
- `artifacts/funding_dashboard.csv`
- `artifacts/departmental_performance_profiles.md`
- `artifacts/source_quality_notes.md`
- `topics/data/processed/federal_awards_rutgers_fy2021_fy2025.csv`

## Next Research Step

Join the public award panel to Rutgers internal sponsored-program account data, PI appointments, department/campus mappings, and faculty headcount before producing operational department rankings.
