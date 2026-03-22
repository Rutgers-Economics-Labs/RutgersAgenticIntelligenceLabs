# Gap-Closing Roadmap

This roadmap replaces the older generic phase plan with a gap-closing plan based on the current codebase.

RAIL today is best described as an AI-assisted ontology research workbench:
- Next.js dashboard and workspace UI
- FastAPI orchestration layer
- Convex-backed metadata/config/session store
- YAML-driven hydration engine
- ontology + DuckDB query surface
- single generalist tool-using agent

The remaining work is not "build the app from scratch." It is closing the gap from that workbench to the full AI-native research platform vision in [platform-vision.md](/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/goals/platform-vision.md).

---

## Current Gap Summary

### Strong Today
- Config-driven ingestion for APIs, CSV/Excel, scrape previews, and document previews
- ontology hydration and ontology/graph/entity query surfaces
- DuckDB SQL mirror and Python execution
- dashboard/workspace/product shell
- registry-assisted source discovery

### Still Missing
- autonomous discovery and refresh of sources
- specialized multi-agent orchestration
- first-class econometric workflows
- stale-analysis detection and auto-refresh
- reproducibility, sharing, and provenance
- production-grade ops, auth, and background scheduling

---

## Delivery Strategy

The work should be closed in four waves:
1. Finish ingestion autonomy and data freshness.
2. Add agent specialization and research-grade analysis modules.
3. Add reproducibility, sharing, and monitoring.
4. Harden operations, auth, and scale behavior.

This preserves momentum because each wave builds on code already in place rather than introducing a parallel architecture.

---

## Wave 1: Ingestion Autonomy

### Goal
Move from "known-source ingestion" to "researcher can point at almost anything and hydrate it reliably."

### Gap Being Closed
- incomplete scrape/document ingestion
- no unstructured normalization
- no incremental ingestion
- registry is curated, not yet part of a self-updating ingestion loop

### Work Orders
- WO-11 Web Scraping Agent
  Current status: partial
  Static HTML table preview exists; JS-rendered scraping, richer extraction, and full agent flow remain.
- WO-12 PDF / Document Parsing
  Current status: partial
  Table extraction exists; prose extraction and more robust document handling remain.
- WO-13 Unstructured Normalization Plugin
  Current status: open
- WO-15 Incremental Ingestion
  Current status: open
- WO-24 Staleness Detection
  Current status: open
- WO-34 Background Scheduler
  Current status: open

### Highest-Leverage Sequence
1. Finish WO-11 with Playwright and agent-facing source capture.
2. Finish WO-12 with prose extraction and LLM normalization path.
3. Build WO-13 so messy source outputs can be normalized into stable pipeline inputs.
4. Build WO-15 so hydrated sources can update cheaply.
5. Build WO-24 and WO-34 together so data freshness becomes visible and actionable.

### Exit Criteria
- researcher can give a URL or document and get a usable config without hand-authoring YAML
- updated sources can refresh without full rebuilds
- platform can detect and schedule refresh work

---

## Wave 2: Agent Specialization And Research Modules

### Goal
Move from one generalist tool caller to a coordinated research workflow.

### Gap Being Closed
- no specialist agents
- no explicit coordinator workflow
- no first-class econometric modules

### Work Orders
- WO-16 Data Engineer Agent
  Current status: open
- WO-17 Analyst Agent
  Current status: open
- WO-18 Agent Teaming
  Current status: open
- WO-19 DiD Module
  Current status: open
- WO-20 Panel Regression Module
  Current status: open
- WO-21 Event Study Module
  Current status: open
- WO-22 Synthetic Control Module
  Current status: open

### Highest-Leverage Sequence
1. WO-16 first
   This upgrades data acquisition, config generation, and hydration QA.
2. WO-19 and WO-20 next
   These create structured analysis surfaces the analyst agent can reliably call.
3. WO-17 after the first econometric modules exist
   Otherwise the analyst agent still falls back to ad-hoc Python too often.
4. WO-18 last in this wave
   Coordinator/teaming makes sense once the specialist roles and modules are real.
5. WO-21 and WO-22 after the core analyst path is stable.

### Exit Criteria
- researcher prompt can trigger a multi-step acquisition + hydration + analysis workflow
- core econometric analyses are structured platform features, not just sandbox code

---

## Wave 3: Reproducibility, Sharing, And Research Productization

### Goal
Turn analysis results into durable, inspectable research artifacts rather than ephemeral runs.

### Gap Being Closed
- weak provenance
- no dependency graph for analyses
- no versioned outputs
- no sharing/export/citation workflow

### Work Orders
- WO-23 Dependency Graph
  Current status: open
- WO-25 Versioned Analysis Outputs
  Current status: open
- WO-26 Analysis Provenance
  Current status: open
- WO-27 Export Formats
  Current status: open
- WO-28 Shareable Links
  Current status: open

### Highest-Leverage Sequence
1. WO-23 dependency tracking
2. WO-25 versioned outputs
3. WO-26 provenance capture
4. WO-27 exports
5. WO-28 shareable links

### Why In This Order
- sharing and exports are much more valuable once outputs are versioned and attributable
- stale analysis and refresh logic depend on the dependency layer

### Exit Criteria
- each analysis run can be traced back to data, code, model, and hydration job
- results can be compared across runs and shared externally

---

## Wave 4: Monitoring, Auth, And Operational Hardening

### Goal
Make the platform sustainable as an always-on multi-user system.

### Gap Being Closed
- limited operational visibility
- weak auth and user boundary model
- single-path worker behavior
- infrastructure/scaling gaps

### Work Orders
- WO-29 Research Dashboard
  Current status: open
- WO-30 Ontology Health Panel
  Current status: open
- WO-31 Time-Series Monitor
  Current status: open
- WO-32 Multi-Pipeline Parallelism
  Current status: open
- WO-33 S3 Artifact Storage
  Current status: partial scaffolding
- WO-35 API Authentication
  Current status: open
- WO-36 Cursor Pagination
  Current status: open

### Highest-Leverage Sequence
1. WO-35 auth
2. WO-33 artifact storage
3. WO-29 dashboard
4. WO-30 health panel
5. WO-32 parallelism
6. WO-31 time-series monitor
7. WO-36 pagination where query volume justifies it

### Exit Criteria
- platform has user boundaries, durable artifact storage, and operational visibility
- hydration can scale past one-at-a-time workflows

---

## Recommended Immediate Roadmap

If the goal is to maximize product leverage with the current architecture, the next recommended sequence is:

1. Finish WO-11
   Reason: closes the most visible ingestion gap from the registry/config work.
2. Finish WO-12
   Reason: makes document ingestion genuinely useful rather than table-only.
3. Build WO-13
   Reason: unstructured normalization makes scrape/document pipelines durable.
4. Build WO-15
   Reason: reduces ingestion cost and enables freshness workflows.
5. Build WO-16
   Reason: turns the stronger ingestion layer into a specialist agent capability.
6. Build WO-19 and WO-20
   Reason: these are the first analyst-grade platform features.
7. Build WO-23, WO-25, and WO-26
   Reason: these convert analyses into durable research artifacts.

This path closes the largest product and architecture gaps without reworking the existing stack.

---

## Dependency Notes

- WO-13 depends on finishing the richer extraction paths from WO-11 and WO-12.
- WO-15 pairs naturally with WO-24 and WO-34.
- WO-17 depends on at least one structured analysis module from WO-19 to WO-22.
- WO-18 depends on WO-16 and WO-17.
- WO-25 and WO-26 depend on WO-23.
- WO-28 is much stronger after WO-25 and WO-26.
- WO-29 and WO-30 become much more valuable after WO-24, WO-25, and WO-26.
- WO-32 and WO-33 should be treated as operational prerequisites for sustained scheduled refresh.

---

## Deliverables By Stage

### End of Wave 1
- broad ingestion coverage
- refresh-aware pipelines
- source freshness visibility

### End of Wave 2
- specialist agents
- first-class econometric analysis features
- coordinated acquisition-to-analysis workflows

### End of Wave 3
- reproducible, versioned, shareable research outputs

### End of Wave 4
- multi-user, monitored, operationally durable platform
