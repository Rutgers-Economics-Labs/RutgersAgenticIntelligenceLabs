# Work Order 06 — Auto-Schema Inference UI

## Goal
Add a "Generate from sample" flow to the Configs page that lets a researcher paste a CSV header or JSON sample and have the AI suggest ready-to-save API and ontology YAML configs.

## Current State
`POST /api/v1/agent/infer-schema` exists and works. No frontend exposes it.

## Steps

### 1. Add "Generate from sample" button to Configs page
File: `packages/web/app/(dashboard)/configs/page.tsx`

Add a button in the header area of the Configs page:
```
[+ New Config]  [✦ Generate from sample]
```

### 2. Build the inference modal
A multi-step modal:

**Step 1 — Input**
- Radio: "Paste CSV header / data sample" or "Describe the data"
- Textarea for the sample (CSV rows or JSON)
- Text input for description (optional, always shown)
- Model selector (reuse the agent model list from `GET /agent/models`)
- "Generate" button → calls `agent.inferSchema(sample, description, model)`

**Step 2 — Review (shown after API returns)**
Two side-by-side panels:
- Left: "API Config YAML" — Monaco-style textarea pre-filled with `api_yaml`
- Right: "Ontology Config YAML" — pre-filled with `ontology_yaml`
- Below: explanation text from `explanation` field
- Both panels are editable before saving

**Step 3 — Name & Save**
- Two name/slug inputs (one per config)
- "Save Both" button → calls `configs.create("apis", ...)` and `configs.create("ontologies", ...)` via `lib/api.ts`
- On success: closes modal, reactive list updates

### 3. Handle loading and error states
- Show spinner + "Generating configs…" during the API call
- Show error inline if the API returns non-2xx
- "Try again" resets to Step 1

### 4. Add `agent.inferSchema` call to `lib/api.ts`
Already exists. No change needed.

## Affected Files
- `packages/web/app/(dashboard)/configs/page.tsx` — add Generate button + modal

## Acceptance Criteria
- [ ] "Generate from sample" button visible on Configs page
- [ ] Pasting 5 rows of CSV and clicking Generate returns two YAML blocks
- [ ] Both YAML blocks are editable before saving
- [ ] Clicking "Save Both" creates both configs and they appear in the reactive list
- [ ] Error state shows if API fails (e.g. no LLM key configured)
