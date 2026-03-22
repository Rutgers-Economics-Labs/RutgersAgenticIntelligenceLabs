# Work Order 20 — Panel Regression Module

## Layer
4 — Econometric Analysis Modules

## Goal
Build a config-driven panel regression module supporting fixed effects, random effects, and pooled OLS with automatic Hausman test, clustered standard errors, and publication-ready output.

## Steps

### 1. Panel regression analysis plugin
File: `packages/engine/analysis/panel_regression.py`

```python
NAME = "panel_regression"
DESCRIPTION = "Fixed effects, random effects, or pooled OLS panel regression."

def run(onto, config: dict) -> dict:
    """
    config:
      outcome:         OWL data property name
      predictors:      list of OWL property names
      entity_effects:  bool (default true)
      time_effects:    bool (default false)
      estimator:       "fe" | "re" | "pooled" | "auto"
                       "auto" runs Hausman test and selects FE or RE
      se:              "standard" | "robust" | "clustered"
      cluster_by:      "entity" | "time" | "two-way" (required if se=clustered)
      absorb:          list of categorical variables to absorb as fixed effects
    """
```

### 2. Dataset construction
Same approach as WO-19: build panel from ontology Measure instances linked to entities. Rows = entity-period, columns = outcome + predictors.

Handle unbalanced panels (missing observations for some entity-period combinations) by flagging them and reporting coverage.

### 3. Hausman test (for `estimator: "auto"`)
Run both FE and RE estimators, perform Hausman test, select FE if null is rejected (p < 0.05), RE otherwise. Report test statistic and decision in the output.

### 4. Result sections
```python
{
  "title": "Panel Regression: {outcome} ~ {predictors}",
  "sections": [
    {"type": "metrics", "items": [
      {"label": "R²", "value": ...},
      {"label": "N (obs)", "value": ...},
      {"label": "N (entities)", "value": ...},
      {"label": "Estimator", "value": "Fixed Effects"},
    ]},
    {"type": "table", "title": "Coefficient Table",
     "columns": ["Variable", "Coef", "SE", "t", "p", "[95% CI]"],
     "data": [...]
    },
    {"type": "text", "content": "Hausman test: chi2={...}, p={...}. Selected: FE."},
    {"type": "chart", "title": "Coefficient Plot", "data": [...], "x": "variable", "y": "coef"},
  ]
}
```

### 5. Coefficient plot
A horizontal bar chart showing coefficients with 95% CI error bars. Error bar rendering requires the chart section to support a `ci_low` / `ci_high` column — extend the frontend chart renderer to support this.

### 6. Agent tool: `run_panel_regression`
Add to `agent_service.py` and `analyst_agent.py`.

### 7. Dependencies
- `linearmodels>=6.0` — already added in WO-19

## Affected Files
- `packages/engine/analysis/panel_regression.py` — **create**
- `packages/api/app/services/agent_service.py` — add tool
- `packages/api/app/services/analyst_agent.py` — add tool (WO-17)
- `packages/web/app/(dashboard)/analysis/page.tsx` — extend chart renderer for CI bars
- `specs/plugins.md` — document plugin

## Acceptance Criteria
- [ ] `estimator: "auto"` runs Hausman test and selects the correct estimator
- [ ] Clustered SEs produce different (larger) SEs than standard errors on the same data
- [ ] Unbalanced panel is handled without crashing — coverage report included
- [ ] Coefficient plot renders with visible error bars in the Analysis UI
- [ ] Plugin is callable from agent via `run_panel_regression` tool
