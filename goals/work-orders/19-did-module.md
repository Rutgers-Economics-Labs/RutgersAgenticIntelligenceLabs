# Work Order 19 — Difference-in-Differences Analysis Module

## Layer
4 — Econometric Analysis Modules

## Goal
Build a first-class DiD analysis module that takes a YAML config, assembles the panel dataset from the ontology, tests parallel trends, runs the estimator, and returns a structured result with coefficient plot, event study, and result table.

## Background
DiD is the most common causal inference design in applied economics. Today a researcher has to write this from scratch in the code sandbox. A structured module encodes best practices (parallel trends test, clustered SEs, staggered adoption handling) and makes results reproducible and comparable across studies.

## Steps

### 1. DiD analysis plugin
File: `packages/engine/analysis/did_analysis.py`

Follows the existing analysis plugin contract (`specs/plugins.md`):
```python
NAME = "did_analysis"
DESCRIPTION = "Difference-in-differences estimator with parallel trends test and event study."

def run(onto, config: dict) -> dict:
    """
    config:
      outcome:          OWL data property name (e.g. hasIncome)
      treatment_uri_pattern: regex matching treated entity URIs (e.g. "County_34.*")
      treatment_date:   ISO date string
      pre_periods:      int (number of pre-treatment periods to use)
      post_periods:     int
      covariates:       list of OWL property names (optional)
      clustered_se:     "entity" | "time" | "two-way" | null
      estimator:        "twfe" | "cs" | "sa"  (TWFE, Callaway-Sant'Anna, Sun-Abraham)
    Returns: AnalysisResult dict
    """
```

### 2. Dataset construction
The plugin builds a balanced panel from the ontology:
- Iterates `Measure` instances linked to each entity in the treatment/control group
- Pivots to wide format: rows = entity-period, columns = outcome + covariates
- Assigns treatment indicator based on `treatment_uri_pattern` and `treatment_date`

### 3. Parallel trends test
Before running DiD, test parallel trends:
- Plot pre-period trends for treatment and control groups
- Run a linear test: regress outcome on `treatment * time_trend` in pre-period only
- Report the F-statistic and p-value
- If p < 0.1: add a warning section to the result

### 4. Estimator implementations
**TWFE (default):** Standard two-way fixed effects via `linearmodels.PanelOLS`.

**Callaway-Sant'Anna (cs):** Use `csdid` Python package if available; fall back to TWFE with a warning if not installed.

**Sun-Abraham (sa):** Use `pyfixest` if available; fall back.

All estimators return: coefficient, SE, 95% CI, p-value for the ATT.

### 5. Event study
Compute dynamic treatment effects for each period relative to treatment:
- Coefficients for periods `[-pre_periods, ..., -1, 0, 1, ..., post_periods]`
- Omit period -1 (reference period)
- Return as a list of `{period, estimate, ci_low, ci_high}` for the frontend chart

### 6. Structured result output
Returns an `AnalysisResult` with sections:
```python
{
  "title": "DiD Analysis: {outcome} — {treatment_date}",
  "sections": [
    {"type": "metrics", "items": [{"label": "ATT", "value": "..."}, {"label": "p-value", ...}]},
    {"type": "text", "content": "Parallel trends test: F={...}, p={...}"},
    {"type": "chart", "title": "Event Study", "data": [...], "x": "period", "y": "estimate"},
    {"type": "table", "title": "Coefficient Table", "columns": [...], "data": [...]},
    {"type": "text", "content": "Interpretation: ..."}  # LLM-generated if AI available
  ]
}
```

### 7. Agent tool: `run_did_analysis`
File: `packages/api/app/services/agent_service.py` and `analyst_agent.py`

```python
{
  "name": "run_did_analysis",
  "description": "Run a DiD analysis using the structured module. Provide outcome property, treatment group pattern, and treatment date.",
  "parameters": { ... }
}
```

Tool calls `POST /api/v1/analysis/plugins/did_analysis/run` with the config.

### 8. Direct API endpoint
Already handled by existing `POST /api/v1/analysis/plugins/{slug}/run`. No new routes needed.

### 9. New Python dependencies
- `linearmodels>=6.0` (already partially available via statsmodels)
- `pyfixest` (optional, for Sun-Abraham)
- Add to `packages/engine/pyproject.toml`

### 10. DiD config YAML schema
Add `type: did` to the analysis config spec in `specs/yaml-config.md` (engine specs).

## Affected Files
- `packages/engine/analysis/did_analysis.py` — **create**
- `packages/api/app/services/agent_service.py` — add `run_did_analysis` tool
- `packages/api/app/services/analyst_agent.py` — add tool (when WO-17 complete)
- `packages/engine/pyproject.toml` — add linearmodels, pyfixest (optional)
- `specs/plugins.md` — document new built-in plugin
- `specs/yaml-config.md` — document DiD analysis config

## Acceptance Criteria
- [ ] Plugin runs end-to-end on NJ county data and returns a populated AnalysisResult
- [ ] Parallel trends test result included in output
- [ ] Event study section contains one point per period with confidence intervals
- [ ] TWFE estimator produces correct ATT with clustered SEs
- [ ] Agent can trigger the DiD module by calling `run_did_analysis` tool
- [ ] Weak parallel trends (p < 0.1) generates a warning section in the result
