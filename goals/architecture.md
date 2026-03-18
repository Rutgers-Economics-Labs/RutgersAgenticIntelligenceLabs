# System Architecture & Methodology

The project will be implemented as a modular pipeline consisting of four core layers:

## 1. Data Ingestion Layer
**Objective:** Enable on-demand acquisition of data from diverse formats and web sources.
- **Capabilities:**
  - Load structured files: CSV, JSON, Excel, Parquet.
  - Download data from URLs automatically.
  - Scrape tabular data from websites.
  - Extract structured information from PDFs.
  - Parse APIs (e.g., economic data portals).
  - Handle compressed archives (ZIP, TAR).
  - Convert unstructured data into structured tabular form using LLM-assisted parsing when necessary.
- **Agent Capabilities:**
  - Given a link, detect file types and recursively download required assets.
  - Infer schema and variable meanings.
  - Log metadata (source URL, timestamp, update frequency).
  - Store raw data and cleaned data separately.
- **Deliverable Output:** Standardized internal data store, version-controlled datasets, and a metadata registry.

## 2. Ontology & Data Normalization Layer
**Objective:** Convert raw datasets into a unified schema that enables cross-dataset integration. The core ontology will be highly robust, but **AI agents can dynamically propose and apply schema extensions** when encountering new entity types.
- **Components:**
  - Standardized keys (time, geography, entity, treatment group).
  - Variable tagging (e.g., employment, GDP, prices, demographics).
  - Unit harmonization (real vs nominal, inflation adjustment).
  - Geographic crosswalks (FIPS, ZIP, county, state).
  - Temporal harmonization (daily, monthly, quarterly, annual).
- **Ontology Structure:**
  - Entities (firms, households, counties, states).
  - Measures (outcomes, treatments, controls).
  - Dimensions (time, geography, demographic group).
This layer ensures analyses do not break when new data is ingested.

## 3. Analysis Framework Layer
**Objective:** Provide reusable, generalized econometric and data science pipelines. **AI Analyst Agents will write custom Python code** (leveraging libraries like `statsmodels`, `linearmodels`, etc.) to execute these modules on demand.
**Initial built-in modules:**
- **A. Difference-in-Differences (DiD):** Automatic treatment/control identification, pre-trend diagnostics, dynamic event study specification, robust standard errors, staggered adoption support.
- **B. Panel Regression Framework:** Fixed/random effects, clustered standard errors, instrumental variables support.
- **C. Time Series Framework:** ARIMA and distributed lag models, forecast evaluation, structural break detection.
- **D. Descriptive & Exploratory Modules:** Automated summary statistics, correlation matrices, visualization generation, missing data diagnostics.
**Each module:** Accepts standardized dataset input, automatically maps variables via ontology tags, and re-runs when data updates.

## 4. Automation & Self-Updating Mechanism
**Objective:** Ensure that analyses update automatically when data changes.
- **Features:** Data source monitoring, scheduled refresh jobs, dependency graph linking datasets to analyses, recomputing only affected pipelines, cached intermediate results, versioned outputs.
- Researchers should not need to modify code when new time periods are added, additional observations are appended, or minor schema changes occur.

---

## Core Technical Components
The framework will be implemented in Python using a modular architecture. It will include a persistent metadata database, a version-controlled dataset registry, and logging mechanisms to ensure reproducibility. A command-line interface will enable researchers to load data, run analyses, and monitor update cycles. For visualization, the system will support both structured JSON interfaces (like Streamlit) and **agents writing and deploying custom UI code (e.g., React/Next.js) directly**. Automatic documentation generation will describe dataset schemas, transformations, and model specifications.

## Data Sources (Initial Integration Targets)
The framework will be designed to support integration with:
- U.S. Census ACS
- Bureau of Labor Statistics (BLS)
- FRED API
- BEA datasets
- State-level open data portals
- Custom researcher-uploaded datasets
- PJM, EIA, FERC energy datasets
- Web-scraped regulatory filings

The system must be extensible to additional APIs and institutional data portals.
