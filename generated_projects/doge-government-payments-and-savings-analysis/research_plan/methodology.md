# Methodology

## Initial Approach

1. Use the OpenAPI specification as the contract for endpoint shape and field
   availability.
2. Sample live responses from `/payments` and `/payments/statistics`.
3. Build a descriptive profile of:
   - payment counts by agency
   - payment counts by date
   - frequent recipient organizations
   - amount distribution and outliers
4. Read recipient and agency justifications as text fields suitable for later
   qualitative review or NLP scoring.
5. Compare payment coverage claims in the docs against actual observed data
   coverage before making any broad conclusions about federal spending.
6. Treat DOGE savings endpoints as adjacent but analytically distinct from the
   payment data unless shared identifiers make direct linkage possible.

## Guardrails

- Do not infer full federal coverage from the current payments feed.
- Separate documented API capability from validated empirical findings.
- Record every downstream claim with endpoint provenance and extraction date.
