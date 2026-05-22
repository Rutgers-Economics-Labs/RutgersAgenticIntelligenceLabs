# Verification Certificate: NJ Housing Affordability Analysis

**What was analyzed:**
Housing affordability and labor-market linkage in New Jersey (2015–2025) using FRED series NJSTHPI, NJURN, and CPIAUCSL.

**Sources:**
- NJSTHPI: https://fred.stlouisfed.org/series/NJSTHPI
- NJURN: https://fred.stlouisfed.org/series/NJURN
- CPIAUCSL: https://fred.stlouisfed.org/series/CPIAUCSL

**Key findings (from hydrated DuckDB):**
- NJ House Price Index: 472.09 → 939.31 (+99.0% nominal)
- Real housing change (nominal minus CPI): +57.4%
- NJ unemployment: 6.9% → 4.7%

**Verification status:** partially_verified
**Generated at:** 2026-05-19T15:16:55Z
**Live loop:** `packages/api/scripts/run_live_agent_loop.py`
