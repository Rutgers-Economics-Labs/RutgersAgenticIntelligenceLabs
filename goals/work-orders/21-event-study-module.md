# Work Order 21 — Event Study Module

## Layer
4 — Econometric Analysis Modules

## Goal
Build an event study analysis module that plots dynamic treatment effects around a policy event date, with pre-trend tests and publication-ready output.

## Steps

### 1. Event study analysis plugin
File: `packages/engine/analysis/event_study.py`

```python
NAME = "event_study"
DESCRIPTION = "Dynamic treatment effects (event study) around a policy date."

def run(onto, config: dict) -> dict:
    """
    config:
      outcome:              OWL data property name
      treatment_uri_pattern: regex matching treated entity URIs
      event_date:           ISO date string (the policy/event date)
      window_before:        int (periods before event, default 4)
      window_after:         int (periods after event, default 4)
      control_uri_pattern:  optional; defaults to all non-treated entities
      covariates:           list of property names (optional)
      se:                   "standard" | "clustered"
    """
```

### 2. Estimation approach
- Construct relative-time variable: `t = period - event_period`
- Run TWFE with dummies for each `t` in `[-window_before, ..., -1, 1, ..., window_after]`
- Omit `t = -1` as reference period
- Return coefficient + 95% CI for each `t`

### 3. Pre-trend test
- Test whether pre-event coefficients are jointly zero: F-test on `t ∈ [-window_before, ..., -2]`
- Report F-statistic, p-value, and plain-English conclusion
- If p < 0.1: add a warning section

### 4. Result sections
```python
{
  "title": "Event Study: {outcome} around {event_date}",
  "sections": [
    {"type": "chart", "title": "Dynamic Treatment Effects",
     "data": [{"period": -4, "estimate": ..., "ci_low": ..., "ci_high": ...}, ...],
     "x": "period", "y": "estimate"},
    {"type": "metrics", "items": [
      {"label": "Pre-trend F-stat", "value": ...},
      {"label": "Pre-trend p-value", "value": ...},
    ]},
    {"type": "text", "content": "Pre-trend test: ..."},
    {"type": "table", "title": "Coefficients by Period", "columns": [...], "data": [...]}
  ]
}
```

### 5. Event study chart rendering
The event study chart needs a vertical dashed line at `period = 0` (the event date) and a horizontal line at `y = 0` (null effect). Extend the frontend chart renderer in the Analysis page to support these reference lines via optional `reference_lines: [{x: 0, label: "Event"}, {y: 0}]` field in the chart section.

### 6. Agent tool: `run_event_study`
Add to `agent_service.py` and `analyst_agent.py`.

## Affected Files
- `packages/engine/analysis/event_study.py` — **create**
- `packages/api/app/services/agent_service.py` — add tool
- `packages/api/app/services/analyst_agent.py` — add tool (WO-17)
- `packages/web/app/(dashboard)/analysis/page.tsx` — extend chart for reference lines + CI bands
- `specs/plugins.md` — document plugin

## Acceptance Criteria
- [ ] Event study returns one coefficient per period in the window
- [ ] Pre-trend test result included; warning shown if pre-trends detected
- [ ] Event study chart shows reference lines at period=0 and y=0
- [ ] CI bands (shaded area) visible around the point estimates in the chart
- [ ] Tool accessible to both generalist and Analyst agents
