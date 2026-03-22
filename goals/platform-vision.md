# RAIL Platform Vision

Rutgers Agentic Intelligence Labs — complete platform vision.

RAIL is an open-source, AI-native research platform for economic data science. The full vision is a system where a researcher describes a question, and a team of AI agents autonomously assembles the data, builds the knowledge graph, runs the analysis, and maintains the results as data updates — with the researcher steering, not scripting.

Think: Palantir's data integration + Databricks' compute + an autonomous research team, open-source and domain-agnostic.

---

## What Is Built Today

- YAML-driven hydration engine (Census, FRED, World Bank, CSV/Excel)
- OWL knowledge graph (owlready2 + SQLite) with ~1,500 NJ/NY entities
- FastAPI service with ontology query, config CRUD, and job management endpoints
- DuckDB SQL mirror of the ontology, rebuilt after every hydration
- Python code execution sandbox (pandas, statsmodels, sklearn, matplotlib)
- Provider-agnostic AI agent (LiteLLM: Claude, Gemini, GPT-4o, OpenRouter)
- Streaming workspace UI with tool call transparency
- SQL explorer with NL→SQL
- Next.js + Convex real-time frontend

---

## What Remains to Be Built

### Layer 1 — Completeness (missing UI and polish)

These finish features that are partially built.

| Feature | Work Order |
|---------|-----------|
| End-to-end environment validation | WO-03 |
| Entity detail page (`/explorer/[id]`) | WO-04 |
| Project forking | WO-05 |
| Auto-schema inference UI in Configs | WO-06 |
| Workspace session persistence | WO-07 |
| Job detail page with step timeline + logs | WO-08 |
| Statistical analysis templates | WO-09 |
| Semantic / embedding-based search | WO-10 |

---

### Layer 2 — Ingestion Expansion

The current engine handles HTTP APIs, CSV, and Excel. The full vision requires ingesting anything a researcher points at.

**Web scraping agent**
An agent that accepts a URL, fetches the page, extracts tabular or structured data, and generates an API config YAML automatically. Powered by LLM extraction + BeautifulSoup/Playwright for JS-rendered pages.

**PDF and document parsing**
Accept PDFs, Word documents, and plain text. Extract tables via `pdfplumber` or `camelot`. Extract prose statistics via LLM (e.g. "extract all numerical claims from this Federal Reserve report"). Output is structured rows that feed the hydration pipeline.

**Unstructured data normalization**
A transform plugin that accepts messy free-text columns (e.g. "Northeast region, Q3 2022") and uses an LLM to normalize them into structured fields (region code, year, quarter).

**Data source registry**
A searchable catalog of known public data sources (Census variables, FRED series IDs, World Bank indicators, BLS codes). The agent can search this registry when deciding what data to fetch, rather than hallucinating endpoint URLs.

**Incremental / delta ingestion**
Instead of re-running a full pipeline when data updates, track the last-fetched state per API source and fetch only new records. Reduces hydration time from minutes to seconds for incremental sources.

---

### Layer 3 — AI Agent Specialization

The current agent is a single generalist. The full vision uses specialized agent roles that hand off to each other.

**AI Data Engineer Agent**
Specialized for: discovering data sources, writing and validating YAML configs, running hydration pipelines, monitoring data quality.

Capabilities beyond current agent:
- Proactively suggests new data sources relevant to the research question
- Validates that fetched data actually contains expected fields before mapping to ontology
- Detects schema drift (a data source changed its response format) and proposes config fixes
- Runs automated data quality checks (missing values, outliers, date coverage gaps)

**AI Analyst Agent**
Specialized for: statistical analysis, econometric modeling, visualization, interpretation.

Capabilities beyond current agent:
- Knows econometric best practices (instrument selection, parallel trends testing, covariate balance)
- Chooses the right estimator for the research design automatically
- Produces APA-style result tables and interprets coefficients in plain English
- Flags threats to validity (confounders, sample selection, measurement error)

**Agent Teaming Protocol**
When a researcher submits a question:
1. Coordinator agent decomposes the question into data needs and analysis needs
2. Data Engineer agent handles data acquisition and hydration
3. Analyst agent receives the hydrated graph and runs the analysis
4. Results returned to researcher with full provenance chain

Implemented as a multi-step agent workflow in `agent_service.py`, with each role using a different system prompt and tool set.

---

### Layer 4 — Econometric Analysis Modules

Beyond ad-hoc Python in the sandbox, RAIL should have structured, configurable analysis modules that encode best practices.

**Difference-in-Differences (DiD) Module**
A first-class analysis type, not just a code template.

Config structure:
```yaml
type: did
outcome: hasIncome
treatment_group: counties_with_policy
control_group: counties_without_policy
treatment_date: "2020-01-01"
covariates: [hasPopulation, hasFIPS]
clustered_se: state
```

The module:
- Builds the panel dataset from the ontology
- Runs parallel trends test and reports results
- Runs the DiD estimator (standard 2x2 and staggered via `did` package)
- Produces coefficient plot, event study plot, and result table
- Returns a structured `AnalysisResult` with all sections

**Panel Regression Module**
Config-driven fixed effects / random effects regression using `linearmodels`.

```yaml
type: panel
outcome: hasValue
predictors: [hasPopulation, hasFIPS]
entity_effects: true
time_effects: true
se: clustered
cluster_by: state
```

**Event Study Module**
Plots treatment effect estimates in an event-time window around a policy date.

**Synthetic Control Module**
Constructs a synthetic counterfactual for a treated unit from a donor pool in the ontology.

All modules are exposed as:
- Analysis plugins (existing plugin architecture)
- Agent tools (`run_did_analysis`, `run_panel_regression`, etc.)
- Direct API endpoints (`POST /api/v1/analysis/did`)

---

### Layer 5 — Self-Updating Analyses

One of the core vision goals: analyses automatically refresh when their underlying data updates.

**Dependency graph**
Each analysis result records which ontology individuals and series it depends on. Stored in a `analysisDependencies` Convex table: `{analysisId, entityUri | seriesId}`.

**Staleness detection**
After hydration, compare the new entity/series values against the dependency graph. Flag analyses as `stale` if any input changed.

**Auto-refresh trigger**
When an analysis is marked stale:
- If `auto_refresh: true` in the analysis config: re-run automatically after hydration completes
- Otherwise: show a "Data updated — refresh analysis" banner in the UI

**Versioned analysis outputs**
Each analysis run is stored as a versioned snapshot: `{analysisId, version, inputs_hash, outputs, createdAt}`. Researchers can compare versions to see how results changed with new data.

---

### Layer 6 — Reproducibility and Sharing

**Analysis provenance**
Every analysis result includes:
- Exact pipeline slug and job ID that produced the data
- Code/SQL executed
- Model version and parameters
- Timestamp and entity/series versions used

**Export formats**
- Markdown report (analysis title, methodology, tables, charts as embedded images)
- LaTeX table output for academic papers
- CSV export of any result table
- PNG/SVG export of any figure

**Shareable workspace links**
A workspace session can be published as a read-only URL that anyone can view (no auth required for read). The analysis and all its steps are visible but not editable.

**Citation generation**
Given a data source config (Census, FRED, etc.), generate a properly formatted academic citation for the data used.

---

### Layer 7 — Dashboard and Monitoring

**Research dashboard (homepage)**
The `/` route currently redirects to Explorer. The full dashboard should show:
- Active pipelines and last hydration time
- Stale analyses count
- Recent agent sessions
- Key metrics from the most recent analysis run (configurable)

**Ontology health panel**
- Coverage metrics: what % of entities have each key property
- Freshness: when was each data source last fetched
- Anomaly alerts: entities with values 3σ outside historical range

**Time-series monitor**
A dedicated page for tracking FRED/Census series over time — sparklines for all loaded series, alerting when new data is available upstream.

---

### Layer 8 — Infrastructure and Scale

**Multi-pipeline parallelism**
Currently one pipeline runs at a time. Support concurrent hydration jobs for independent pipelines (different ontology classes, no shared write contention).

**S3/R2 artifact storage**
Already scaffolded (`storage_backend = "s3"`). Needs deployment documentation and testing.

**Background scheduler**
Cron-style triggers for pipeline re-runs: `schedule: "0 6 * * 1"` in pipeline YAML re-runs every Monday at 6am. Implemented via Convex scheduled functions or a lightweight background process.

**API authentication**
Currently no auth. For multi-user or public deployment, add API key authentication on FastAPI routes and Convex function-level access control.

**Streaming result pagination**
Large ontologies (100K+ entities) need cursor-based pagination in the ontology service and DuckDB queries. The current limit-based approach breaks down at scale.

---

## Priority Order for Remaining Work

```
Layer 1 (WO 03–10)         ← complete the current feature set
Layer 2 — Ingestion        ← web scraping + PDF + data registry
Layer 3 — Agent teams      ← Data Engineer + Analyst specialization
Layer 4 — Econ modules     ← DiD, panel, event study as first-class types
Layer 5 — Self-updating    ← dependency graph + auto-refresh
Layer 6 — Reproducibility  ← provenance + export + sharing
Layer 7 — Dashboard        ← monitoring + health panel
Layer 8 — Infrastructure   ← scheduler + auth + scale
```

Layers 1–4 deliver the core research value. Layers 5–8 make it production-grade infrastructure.

---

## Success Criteria (from original vision)

- [ ] A researcher provides a dataset link → DiD analysis runs in under 5 minutes
- [ ] Adding new data automatically refreshes dependent results
- [ ] Multiple datasets join without manual reformatting
- [ ] Analyses are reproducible, versioned, and shareable
- [ ] AI Data Engineer and AI Analyst agents collaborate on a research question end-to-end
