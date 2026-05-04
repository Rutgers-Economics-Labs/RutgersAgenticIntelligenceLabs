# Source Registry

Track required sources, ontology config paths, status, provenance, and gaps.

## Primary Sources

| Source | Purpose | Status | Notes |
| --- | --- | --- | --- |
| DOGE OpenAPI spec (`https://api.doge.gov/openapi.json`) | Ground truth for current endpoints, fields, and documented scope | Ready | Version `0.0.2-beta` observed on May 3, 2026 |
| DOGE `/payments` | Payment line items with agency and recipient justifications | Draft for review | Docs say current scope is limited and will expand |
| DOGE `/payments/statistics` | Aggregated counts by agency, request date, and organization | Draft for review | Useful for quick profiling before deep extraction |
| DOGE `/savings/grants` | Grant savings feed | Draft for review | Candidate comparison source for grant-related payment work |
| DOGE `/savings/contracts` | Contract savings feed | Draft for review | Candidate comparison source for cancellation analytics |
| DOGE `/savings/leases` | Lease savings feed | Draft for review | Candidate comparison source for efficiency narratives |

## Validation Sources

| Source | Purpose | Status | Notes |
| --- | --- | --- | --- |
| USASpending award pages | Cross-check grant and award references exposed by DOGE | Manual review | Some DOGE records include direct links |
| FPDS award pages | Cross-check contract records and status metadata | Manual review | DOGE contract docs expose `fpds_link` fields |
