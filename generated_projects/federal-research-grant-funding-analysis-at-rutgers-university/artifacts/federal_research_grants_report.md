# Federal Research Grant Funding Analysis at Rutgers University

Generated: 2026-05-30T23:04:31Z

## Scope

This local RAIL project summarizes public federal award records matching Rutgers over FY2021-FY2025. It uses USAspending.gov for cross-agency federal assistance coverage and the NSF Awards API for additional research-award detail.

## Key Findings

- The processed public-data panel contains 107 Rutgers-matching award records returned for the FY2021-FY2025 query window totaling $1.45B.
- The largest observed agency total is Department of Health and Human Services with $993.8M across 72 records.
- Public federal award feeds do not provide a reliable Rutgers academic department crosswalk, so department-level performance profiles should be treated as a next-step internal-data join rather than inferred from titles alone.

## Annual Snapshot

| Fiscal year | Award records | Observed amount |
| --- | ---: | ---: |
| 2021 | 6 | $67.4M |
| 2022 | 4 | $21.3M |
| 2023 | 6 | $59.7M |
| 2024 | 3 | $46.6M |
| 2025 | 17 | $12.4M |
| pre-2021 active/continuing | 71 | $1.24B |

## Top Observed Awards

| Source | Award ID | Agency | Amount | Program or title |
| --- | --- | --- | ---: | --- |
| USAspending.gov | U24MH068457 | Department of Health and Human Services | $179.7M | COOPERATIVE AGREEMENT (B) |
| USAspending.gov | P425F200193 | Department of Education | $157.6M | FORMULA GRANT (A) |
| USAspending.gov | P425E200365 | Department of Education | $128.3M | FORMULA GRANT (A) |
| USAspending.gov | P30CA072720 | Department of Health and Human Services | $68.2M | PROJECT GRANT (B) |
| USAspending.gov | U54AR055073 | Department of Health and Human Services | $64.0M | COOPERATIVE AGREEMENT (B) |
| USAspending.gov | U45ES006179 | Department of Health and Human Services | $35.9M | COOPERATIVE AGREEMENT (B) |
| USAspending.gov | P30ES005022 | Department of Health and Human Services | $32.0M | PROJECT GRANT (B) |
| USAspending.gov | UL1TR003017 | Department of Health and Human Services | $28.8M | COOPERATIVE AGREEMENT (B) |
| USAspending.gov | P01HL114471 | Department of Health and Human Services | $23.9M | PROJECT GRANT (B) |
| USAspending.gov | U19AI111276 | Department of Health and Human Services | $23.2M | COOPERATIVE AGREEMENT (B) |

## Interpretation Notes

- USAspending award amounts are obligation-style federal award records and may include non-research assistance; filtering to Rutgers and assistance award types gives a broad federal-funding view, not an audited sponsored-research ledger.
- NSF records are useful for research-award detail but overlap with USAspending, so totals should not be added across sources without deduplication.
- A production departmental dashboard should join these public award IDs to Rutgers internal sponsored-program accounts, principal-investigator appointments, and faculty headcount.
