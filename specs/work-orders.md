# Architectural Work Orders: Layered Agent Platform

This document outlines the four sequential work orders required to transition RAIL from a monolithic agent architecture to the **5-Layer Semantic Data OS** model.

---

## [WO-1] Metadata & Coverage (The Gap-Map)
**Status:** Queued
**Objective:** Enable agents to determine if a research question can be answered with the current project graph.

### Key Components
- **`coverage_service.py`**: A new service in `packages/api` that correlates project DuckDB schema with the Registry and Ontology.
- **`coverage.yaml`**: A per-project config file that tracks:
    - Available classes and property density.
    - Time-range coverage (e.g., "NJ Unemployment Rate: 2010-2024").
    - Known data gaps (e.g., "Missing county-level GDP").

---

## [WO-2] Context Assembly Service (The Slicer)
**Status:** Queued
**Objective:** Formalize the creation of "operational slices" to prevent context stuffing.

### Key Components
- **`context_service.py`**: A high-level orchestrator that takes a `planner` manifest and produces a `StructuredContextBundle`.
- **`StructuredContextBundle`**: A frozen JSON/Schema object containing:
    - Scoped DuckDB Views.
    - Snippets from the Knowledge Base.
    - Artifact Version hashes.

---

## [WO-3] Role-Based Agent Runtime (The Orchestrator)
**Status:** Queued
**Objective:** Decompose the research agent into specialized roles with restricted tool access.

### Dedicated Roles
1.  **Planner**: Question decomposition (Tools: `search_ontology`, `list_plugins`).
2.  **Coverage**: Registry matching (Tools: `check_coverage`, `search_registry`).
3.  **Onboarding**: Config synthesis (Tools: `create_api_config`, `run_hydration`).
4.  **Analysis**: Deterministic fact extraction (Tools: `run_sql`, `execute_python`).
5.  **Explanation**: Reporting & Insight (Tools: `generate_report`).

---

## [WO-5] UI: Agentic Observability & Context Dashboard
**Status:** Queued
**Objective:** Provide researchers with visibility into the "operational slice" and agent reasoning chain.

### Key Components
- **Context Viewer**: A component to visualize the `StructuredContextBundle` (active tables, row counts, ontology classes).
- **Role-Based Reasoning Stepper**: A chat UI enhancement that explicitly shows which sub-agent role (Planner, Coverage, etc.) is currently executing.
- **Coverage Heatmap**: A visual overlay in the Schema Browser indicating data density and "hydration status" per class in the current project context.
