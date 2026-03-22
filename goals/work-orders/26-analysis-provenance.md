# Work Order 26 — Analysis Provenance

## Layer
6 — Reproducibility and Sharing

## Prerequisites
WO-25 (Versioned Analysis Outputs)

## Goal
Attach a full provenance record to every analysis result, capturing the exact data sources, pipeline configs, agent messages, and code used to produce it — so findings can be independently reproduced and audited.

## Steps

### 1. Provenance schema
Extend `analysisRuns` in Convex (WO-25) with a `provenance` field:

```ts
provenance: v.optional(v.object({
  pipelineConfigs: v.array(v.object({
    slug: v.string(),
    configYaml: v.string(),       // snapshot of the pipeline YAML at time of run
    jobId: v.optional(v.string()),
  })),
  ontologyClasses: v.array(v.string()),  // OWL classes queried
  sqlQueries: v.array(v.string()),       // SQL statements executed
  pythonCode: v.optional(v.string()),    // code cell that produced the result
  agentMessages: v.array(v.object({     // conversation turns leading to this result
    role: v.string(),
    content: v.string(),
  })),
  modelId: v.string(),                   // e.g. "claude-sonnet-4-6"
  generatedAt: v.number(),
}))
```

### 2. Provenance capture in agent service
In `agent_service.py`, accumulate provenance as the agent loop executes:
- Track every SQL query passed to `run_sql`
- Track every `execute_python` code block
- Track which ontology classes were touched (via `query_ontology` tool args)
- Track which pipeline configs were read (via `list_configs` tool results)
- On analysis completion, attach the full provenance object to the Convex run record

### 3. Config snapshot
When a pipeline config is used in an analysis, snapshot its current YAML into the provenance record. This preserves the exact config at analysis time even if the researcher later edits it.

### 4. Provenance API endpoint
File: `packages/api/app/routers/provenance.py`

```
GET /api/v1/provenance/{run_id}
```

Returns the full provenance object for a given analysis run. Used by the frontend and export features.

### 5. Provenance viewer in UI
In the workspace version history panel (WO-25), add a "Provenance" tab next to "History":

- Show a timeline: **Data Sources → Pipelines → Queries → Analysis Code → Result**
- Each step is expandable to show details (SQL query text, Python code, config YAML)
- A "Reproduce" button assembles a single markdown document from provenance (feeds into WO-27)

### 6. Provenance hash
Compute a SHA-256 hash of the provenance object and store it as `provenanceHash` on the run. Two runs with the same hash are guaranteed identical input conditions.

## Affected Files
- `packages/web/convex/schema.ts` — extend `analysisRuns` with `provenance`
- `packages/api/app/services/agent_service.py` — accumulate and attach provenance
- `packages/api/app/routers/provenance.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/app/(dashboard)/workspace/page.tsx` — provenance viewer tab
- `specs/api.md` — document provenance route

## Acceptance Criteria
- [ ] Every analysis run has a non-empty provenance object
- [ ] Provenance includes all SQL queries and Python code used
- [ ] Config YAML is snapshotted at the time of the run (not the live config)
- [ ] Provenance hash is identical for two runs with the same inputs on the same data
- [ ] Provenance viewer shows timeline in the UI
