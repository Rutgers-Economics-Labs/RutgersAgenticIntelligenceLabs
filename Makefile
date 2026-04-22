.PHONY: help install install-api install-engine install-agent-tools \
        dev api b \
        hydrate hydrate-pipeline hydrate-academic \
        kill kill-api \
        seed \
        test \
        deploy-api \
        clean cache-clear \
        push

ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
VENV     := $(ROOT_DIR).venv
VENV_PY  := $(VENV)/bin/python
# Same effect as `source .venv/bin/activate`: this interpreter + PATH for all recipes.
ifneq ($(wildcard $(VENV_PY)),)
export VIRTUAL_ENV := $(abspath $(VENV))
export PATH       := $(abspath $(VENV)/bin):$(PATH)
PYTHON            := $(abspath $(VENV_PY))
else
PYTHON            := python3
endif
API_DIR  := $(ROOT_DIR)packages/api
ENG_DIR  := $(ROOT_DIR)packages/engine

API_PORT := 8000
PIPELINE           := configs/pipelines/nj_hydration.yaml
ACADEMIC_PIPELINE  := configs/pipelines/academic_hydration.yaml

# ── Env vars — root .env (create locally; not committed) —────────────────────
-include .env
export

# Env block forwarded to the API server (picks up .env values above)
define api_env
	CONVEX_URL="$(CONVEX_URL)" \
	CONVEX_DEPLOY_KEY="$(CONVEX_DEPLOY_KEY)" \
	ENGINE_ROOT="$(ENG_DIR)" \
	RAIL_ANALYSIS_DIR="$(ENG_DIR)/analysis" \
	RAIL_TRANSFORM_DIR="$(ENG_DIR)/transforms" \
	FRED_API_KEY="$(FRED_API_KEY)"
endef

# ─────────────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  RAIL Platform — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    (optional) python3 -m venv .venv   — Makefile uses .venv when present"
	@echo "    make install          Install all dependencies (api + engine)"
	@echo "    make install-api      Install FastAPI service deps"
	@echo "    make install-engine   Install Streamlit/engine deps"
	@echo "    make install-agent-tools Install CLI tools used by agents (grepai + Gemini CLI)"
	@echo ""
	@echo "  Development"
	@echo "    make dev              Start FastAPI only (foreground)"
	@echo "    make api              Start FastAPI only (foreground)"
	@echo "    make kill             Kill FastAPI"
	@echo "    make kill-api         Kill FastAPI on port $(API_PORT)"
	@echo ""
	@echo "  Ontology"
	@echo "    make hydrate          Run default pipeline (nj_hydration)"
	@echo "    make hydrate-academic Academic ontology (CSV demo → academic.db / academic_populated.owl)"
	@echo "    make hydrate-pipeline PIPELINE=path/to/pipeline.yaml"
	@echo "    make seed             Seed backend config state"
	@echo "    make cache-clear      Delete cached API responses"
	@echo ""
	@echo "  Testing"
	@echo "    make test             Run all Python tests (API + engine)"
	@echo ""
	@echo "  Deploy"
	@echo "    make deploy-api       Build and push Docker image to Railway"
	@echo ""
	@echo "  Git"
	@echo "    make push             Push current branch to both origin and personal"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean            Delete generated ontology files + cache"
	@echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Install
# ─────────────────────────────────────────────────────────────────────────────

install: install-api install-engine install-agent-tools

install-api:
	@echo "→ Installing FastAPI deps…"
	$(PYTHON) -m pip install fastapi "uvicorn[standard]" httpx "pydantic>=2.7" \
	  pydantic-settings pyyaml owlready2 "pandas>=2.2" requests openpyxl beautifulsoup4 lxml duckdb aioboto3 litellm matplotlib numpy pdfplumber scikit-learn statsmodels respx pytest-asyncio python-multipart playwright croniter PyJWT

install-engine:
	@echo "→ Installing engine deps…"
	$(PYTHON) -m pip install owlready2 pandas streamlit pyvis requests openpyxl rdflib pyyaml beautifulsoup4 lxml duckdb aioboto3 litellm matplotlib numpy pdfplumber scikit-learn statsmodels python-multipart playwright

install-agent-tools:
	@echo "→ Installing agent CLI tools…"
	brew install yoanbernabeu/tap/grepai
	npm install -g @google/gemini-cli
	@echo "  Installed grepai and Gemini CLI."
	@echo "  Note: Gemini CLI still requires authentication or API credentials on each machine."

# ─────────────────────────────────────────────────────────────────────────────
# Development servers
# ─────────────────────────────────────────────────────────────────────────────

dev: api

api:
	@echo "→ Starting FastAPI on :$(API_PORT)…"
	cd $(API_DIR) && $(api_env) \
	  $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload

b: api

kill: kill-api

kill-api:
	@lsof -ti :$(API_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  API on :$(API_PORT) killed." || echo "  Nothing on :$(API_PORT)."

# ─────────────────────────────────────────────────────────────────────────────
# Ontology hydration
# ─────────────────────────────────────────────────────────────────────────────

hydrate:
	@echo "→ Running pipeline: $(PIPELINE)"
	cd $(ENG_DIR) && FRED_API_KEY=$(FRED_API_KEY) $(PYTHON) hydrate.py --pipeline $(PIPELINE)

hydrate-pipeline:
	cd $(ENG_DIR) && FRED_API_KEY=$(FRED_API_KEY) $(PYTHON) hydrate.py --pipeline $(PIPELINE)

hydrate-academic:
	@echo "→ Academic pipeline: $(ACADEMIC_PIPELINE) (outputs under packages/engine/ontology/)"
	cd $(ENG_DIR) && $(PYTHON) hydrate.py --pipeline $(ACADEMIC_PIPELINE)

seed:
	@echo "→ Seeding Convex with default YAML configs…"
	$(PYTHON) $(ROOT_DIR)scripts/seed_convex.py

cache-clear:
	rm -f $(ENG_DIR)/cache/*.json
	@echo "  Cache cleared."

# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

test:
	@echo "→ Running Python tests (API + engine)…"
	$(PYTHON) -m pytest -v

# ─────────────────────────────────────────────────────────────────────────────
# Deploy
# ─────────────────────────────────────────────────────────────────────────────

deploy-api:
	@echo "→ Deploying API to Railway (push triggers auto-deploy)…"
	@echo "  Ensure railway.json is committed and Railway is linked to this repo."
	@echo "  Run: railway up   (or just push — Railway deploys on every push)"

# ─────────────────────────────────────────────────────────────────────────────
# Git
# ─────────────────────────────────────────────────────────────────────────────

push:
	git -C $(ROOT_DIR) push origin HEAD
	git -C $(ROOT_DIR) push personal HEAD

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

clean: kill
	rm -f $(ENG_DIR)/cache/*.json
	rm -f $(ENG_DIR)/ontology/onto.db $(ENG_DIR)/ontology/onto.db-journal
	rm -f $(ENG_DIR)/ontology/populated_ontology.owl
	rm -f $(ENG_DIR)/graph.html $(ENG_DIR)/graph_full.html
	@echo "  Clean complete."
