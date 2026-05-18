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

The remaining gap is not feature surface area. It is closed-loop trust infrastructure. Five things must be true at the same time before RAIL can be called fully autonomous.

See `goals/roadmap.md` for the five requirements and milestone sequence.
See `docs/future-spec-autonomous-platform-roadmap.md` for the full architecture, audit agent contracts, anti-fabrication system, and lifecycle phases.
See `docs/future-spec-implementation-milestones.md` for the nine milestones organized by package.

---

## Success Criteria

RAIL is autonomous when it can complete multiple end-to-end projects across varied archetypes with:

- no fabricated source or claim promotions
- no hidden state drift between repo, runtime, ontology, and integrity state
- no manual reconciliation required
- no ambiguous blockers in the control plane
- clean audited closeout for every project

Specific research capabilities the platform must deliver:

- [ ] researcher provides a dataset link → ontology-backed analysis runs without manual config authoring
- [ ] adding new data automatically refreshes dependent analyses
- [ ] multiple datasets join without manual reformatting
- [ ] all analyses are reproducible, versioned, and traceable to source
- [ ] specialized agents (data, research, coding, audit) collaborate end-to-end on a research question
