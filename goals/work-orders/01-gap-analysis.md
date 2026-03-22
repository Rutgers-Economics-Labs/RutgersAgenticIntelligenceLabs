# Gap Analysis: Current Spec vs. Vision

The current architecture (as documented in `specs/`) is a solid foundation but represents a **static, manually-configured data pipeline** rather than an **autonomous, agent-driven platform**. 

Here are the primary gaps between what exists today and the ultimate vision:

## 1. Ingestion: Manual YAML vs. AI Data Engineers
- **Current State:** A human researcher must manually write `configs/apis/*.yaml` files, specifying the exact URL, fields, data types, and mapping logic.
- **Vision State:** An "AI Data Engineer" agent takes a prompt (e.g., "Get NJ unemployment data") or a raw URL, automatically downloads/scrapes the data, infers the schema, and generates the pipeline configuration and ingestion Python code.
- **The Gap:** We lack an LLM orchestration layer that can write, test, and commit these API configs autonomously.

## 2. Ontology: Static Schema vs. Dynamic Extension
- **Current State:** The ontology is hardcoded in `configs/ontology/core.yaml`. The engine will crash if a pipeline tries to reference a class or property that isn't explicitly defined there.
- **Vision State:** AI agents dynamically propose schema extensions when they encounter new data types, mapping them into the robustness of the core ontology.
- **The Gap:** The engine (`ontology_builder.py`) needs a mechanism to accept runtime schema extensions or proposals from an agent, validate them against the core, and append them safely.

## 3. Analysis: Static Plugins vs. AI Analyst Agents
- **Current State:** Analysis modules are static Python files dropped into `packages/engine/analysis/`. They execute pre-written pandas/owlready2 logic.
- **Vision State:** "AI Analyst Agents" autonomously write custom Python code using `statsmodels` or `linearmodels` to run Difference-in-Differences, Panel Regressions, etc., based on the data in the ontology.
- **The Gap:** We need an agent workspace that can write, execute, iterate on, and save Python analysis code in a secure Sandbox, feeding the outputs back to the platform.

## 4. UI/Dashboards: Hardcoded Views vs. Dynamic Generation
- **Current State:** The Next.js frontend (`packages/web/`) and Streamlit explorer (`app.py`) have hardcoded UI components for rendering tables and charts.
- **Vision State:** Agents autonomously write and deploy custom React/Next.js UI code or structured JSON to generate bespoke dashboards.
- **The Gap:** The platform needs to support a "UI Generation" pipeline where Next.js pages or Convex schema definitions can be injected or compiled dynamically by the Analyst Agents.
