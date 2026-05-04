# Assumptions

- The primary first-pass analysis will focus on DOGE payment data, not just
  savings data.
- The OpenAPI spec at `https://api.doge.gov/openapi.json` is the most reliable
  machine-readable source for the current endpoint contract.
- The `/payments` dataset is not yet comprehensive for all U.S. government
  payments because the docs explicitly describe it as limited in current scope.
- Cross-source validation may require manual interpretation because shared keys
  across DOGE, USASpending, and FPDS are not guaranteed for every record type.
