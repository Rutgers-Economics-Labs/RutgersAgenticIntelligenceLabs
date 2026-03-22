# Work Order 22 — Synthetic Control Module

## Layer
4 — Econometric Analysis Modules

## Goal
Build a synthetic control analysis module that constructs a weighted counterfactual for a single treated unit from a donor pool in the ontology, for cases where a control group is not available.

## Background
Synthetic control is used when there is a single treated unit (e.g. one state adopts a policy) and the researcher needs to estimate what would have happened without treatment. It weights donor units to match pre-treatment trends.

## Steps

### 1. Synthetic control plugin
File: `packages/engine/analysis/synthetic_control.py`

```python
NAME = "synthetic_control"
DESCRIPTION = "Synthetic control for single treated unit vs donor pool."

def run(onto, config: dict) -> dict:
    """
    config:
      outcome:          OWL data property name
      treated_uri:      exact URI of the treated entity
      donor_uri_pattern: regex matching donor pool URIs
      treatment_date:   ISO date string
      matching_covariates: list of property names to match on in addition to outcome lags
      pre_periods:      int (number of pre-treatment periods to use for weight optimization)
    """
```

### 2. Weight optimization
Use `scipy.optimize.minimize` with SLSQP to find donor weights that minimize the pre-treatment RMSE between the treated unit and the weighted average of donors.

Constraints: weights sum to 1, all weights ≥ 0.

Return the top 5 donors by weight in the output.

### 3. Placebo tests
Run the same synthetic control for each donor unit (treating it as if it were treated). Build a distribution of placebo RMSPE ratios. The treated unit's effect is significant if its post/pre RMSPE ratio is in the top X% of the distribution.

Report: empirical p-value = rank of treated unit / number of placebos.

### 4. Result sections
```python
{
  "title": "Synthetic Control: {treated_uri} — {outcome}",
  "sections": [
    {"type": "chart", "title": "Treated vs Synthetic Control",
     "data": [{period, treated, synthetic}, ...], "x": "period", "y_cols": ["treated", "synthetic"]},
    {"type": "chart", "title": "Placebo Tests",
     "data": [{period, treated_gap, ...placebos}]},
    {"type": "table", "title": "Donor Weights",
     "columns": ["Entity", "Weight"], "data": [...]},
    {"type": "metrics", "items": [
      {"label": "Pre-RMSPE", "value": ...},
      {"label": "Post-RMSPE Ratio", "value": ...},
      {"label": "Empirical p-value", "value": ...},
    ]}
  ]
}
```

### 5. Multi-series chart type
The "Treated vs Synthetic Control" chart needs to render multiple Y series on the same chart. Extend the frontend chart renderer to support `y_cols: string[]` in addition to the existing single `y` field. Use `recharts` `LineChart` with multiple `<Line>` components.

### 6. Agent tool: `run_synthetic_control`
Add to `agent_service.py` and `analyst_agent.py`.

### 7. Dependencies
- `scipy` — for weight optimization (likely already available via statsmodels install)

## Affected Files
- `packages/engine/analysis/synthetic_control.py` — **create**
- `packages/api/app/services/agent_service.py` — add tool
- `packages/api/app/services/analyst_agent.py` — add tool (WO-17)
- `packages/web/app/(dashboard)/analysis/page.tsx` — extend chart for multi-series `y_cols`
- `specs/plugins.md` — document plugin

## Acceptance Criteria
- [ ] Weights sum to 1.0 and are all non-negative
- [ ] Pre-treatment fit (RMSPE) is reported and visibly close to zero in the chart
- [ ] Placebo tests run for all donor units; empirical p-value reported
- [ ] Multi-series chart renders both treated and synthetic lines clearly distinguished
- [ ] Runs on NJ state data with other US states as donor pool
