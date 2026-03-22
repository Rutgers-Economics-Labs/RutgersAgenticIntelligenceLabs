# Work Order 09 — Statistical Analysis Templates

## Goal
Add a library of pre-written Python analysis templates to the Workspace page. Researchers click a template to insert ready-to-run code into a new agent message, rather than writing from scratch.

## Current State
The Workspace page has example prompts for natural-language questions. There are no code templates. The `/execute` endpoint and agent `execute_python` tool are both functional.

## Steps

### 1. Define the template library
Create `packages/web/lib/analysis-templates.ts` with a typed array of templates:

```typescript
export type AnalysisTemplate = {
  id: string
  label: string
  category: "descriptive" | "regression" | "causal" | "timeseries" | "clustering"
  description: string
  prompt: string   // sent as the user message to the agent
  code?: string    // optional pre-written Python (agent will adapt it to actual data)
}
```

**Initial templates to include:**

| ID | Label | Category |
|----|-------|----------|
| `describe-table` | Describe a table | descriptive |
| `top-n` | Top N entities by a column | descriptive |
| `correlation-matrix` | Correlation matrix | descriptive |
| `ols-regression` | OLS regression | regression |
| `panel-fe` | Panel regression (fixed effects) | regression |
| `did-basic` | Difference-in-differences | causal |
| `event-study` | Event study plot | causal |
| `time-series-plot` | Time-series line chart | timeseries |
| `yoy-growth` | Year-over-year growth rates | timeseries |
| `kmeans-cluster` | K-means clustering | clustering |

Each template's `prompt` should be a natural-language instruction that tells the agent what to do and suggests it use `execute_python` with the relevant approach. The agent then adapts it to the actual DuckDB schema.

### 2. Add template panel to Workspace page
Add a collapsible "Templates" section above or beside the input bar. When collapsed, shows a button; when expanded, shows a grid of template cards grouped by category.

Each card:
- Category color dot
- Label
- Description (one line)
- Click → sets `input` to the template's `prompt` and focuses the textarea

### 3. Make prompts schema-aware
Before sending a template prompt, prepend the current SQL schema:
```
[Schema: State(_iri, _id, hasName, hasPopulation, hasFIPS), County(...), ...]
Run a DiD analysis comparing...
```
Fetch the schema once on mount from `sql.schema()` and store in state. Prepend it only for template prompts (not free-form messages).

### 4. Optional: direct code cell
For templates with `code` defined, add a secondary action "Insert code" that adds the code directly into a code cell (for WO-07 workspace cells). Skip until WO-07 is complete.

## Affected Files
- `packages/web/lib/analysis-templates.ts` — **create**
- `packages/web/app/(dashboard)/workspace/page.tsx` — add template panel

## Acceptance Criteria
- [ ] Template panel visible and collapsible on Workspace page
- [ ] All 10 initial templates shown, grouped by category
- [ ] Clicking a template populates the input with the prompt
- [ ] Schema is prepended to template prompts before sending
- [ ] Agent correctly interprets a DiD template prompt and writes/runs code
