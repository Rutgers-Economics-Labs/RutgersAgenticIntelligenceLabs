.PHONY: help install setup install-api install-engine install-web install-agent-tools \
        dev api web frontend run \
        hydrate hydrate-pipeline hydrate-academic \
        kill kill-api kill-web kill-all \
        seed \
        test \
        deploy-api \
        clean cache-clear \
        push \
        install-rail secrets-list

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
WEB_DIR  := $(ROOT_DIR)apps/web

API_PORT := 8000
WEB_PORT := 3000

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
	@echo "  RAIL Platform — Command Center"
	@echo ""
	@echo "  🚀 Setup & Installation"
	@echo "    make setup            One-step install (API + Engine + Web + Seeding)"
	@echo "    make install          Install all dependencies (api + engine + web)"
	@echo "    make install-api      Install FastAPI service deps"
	@echo "    make install-engine   Install Streamlit/engine deps"
	@echo "    make install-web      Install Next.js frontend deps"
	@echo ""
	@echo "  💻 Development"
	@echo "    make run              Start both API and Web (background logs: *.log)"
	@echo "    make api              Start FastAPI only (foreground)"
	@echo "    make web              Start Next.js Command Center (foreground)"
	@echo "    make frontend         Alias for 'make web'"
	@echo ""
	@echo "  🛑 Control"
	@echo "    make kill-all         Kill both API and Web servers"
	@echo "    make kill-api         Kill process on :$(API_PORT)"
	@echo "    make kill-web          Kill process on :$(WEB_PORT)"
	@echo ""
	@echo "  🧠 Ontology & Data"
	@echo "    make hydrate          Run default pipeline (nj_hydration)"
	@echo "    make seed             Seed Convex backend with default configs"
	@echo "    make cache-clear      Delete cached API responses"
	@echo ""
	@echo "  🧪 Testing & Maintenance"
	@echo "    make test             Run all Python tests"
	@echo "    make clean            Reset ontology state + clear cache"
	@echo ""
	@echo "  🛠️ CLI & Secrets"
	@echo "    make install-rail     Install 'rail' CLI in editable mode"
	@echo "    make secrets-list     List project secrets (masked)"
	@echo "    make secrets-set      Set a secret (Usage: make secrets-set KEY=foo VAL=bar)"
	@echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

setup: install seed
	@echo "→ Setup complete. Run 'make run' to start the platform."

install: install-api install-engine install-web install-agent-tools

install-api:
	@echo "→ Installing FastAPI deps…"
	$(PYTHON) -m pip install fastapi "uvicorn[standard]" httpx "pydantic>=2.7" \
	  pydantic-settings pyyaml owlready2 "pandas>=2.2" requests openpyxl beautifulsoup4 lxml duckdb aioboto3 litellm matplotlib numpy pdfplumber scikit-learn statsmodels respx pytest-asyncio python-multipart playwright croniter PyJWT

install-engine:
	@echo "→ Installing engine deps…"
	$(PYTHON) -m pip install owlready2 pandas streamlit pyvis requests openpyxl rdflib pyyaml beautifulsoup4 lxml duckdb aioboto3 litellm matplotlib numpy pdfplumber scikit-learn statsmodels python-multipart playwright

install-web:
	@echo "→ Installing Next.js deps…"
	cd $(WEB_DIR) && npm install

install-agent-tools:
	@echo "→ Installing agent CLI tools…"
	brew install yoanbernabeu/tap/grepai || true
	npm install -g @google/gemini-cli || true

# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

run: kill-all
	@echo "→ Starting RAIL Platform (Logs: backend.log, frontend.log)..."
	@nohup make api > backend.log 2>&1 &
	@nohup make web > frontend.log 2>&1 &
	@echo "  API: http://localhost:$(API_PORT)"
	@echo "  WEB: http://localhost:$(WEB_PORT)"

dev: api

api:
	@echo "→ Starting FastAPI on :$(API_PORT)…"
	cd $(API_DIR) && $(api_env) \
	  $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload

web:
	@echo "→ Starting Next.js on :$(WEB_PORT)…"
	cd $(WEB_DIR) && npm run dev

frontend: web

# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────────────────────

kill-all: kill-api kill-web

kill-api:
	@lsof -ti :$(API_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  API on :$(API_PORT) killed." || echo "  Nothing on :$(API_PORT)."

kill-web:
	@lsof -ti :$(WEB_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  Web on :$(WEB_PORT) killed." || echo "  Nothing on :$(WEB_PORT)."

kill: kill-api

# ─────────────────────────────────────────────────────────────────────────────
# Ontology
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
# Testing & Git
# ─────────────────────────────────────────────────────────────────────────────

test:
	@echo "→ Running Python tests (API + engine)…"
	$(PYTHON) -m pytest -v

deploy-api:
	@echo "→ Deploying API to Railway (push triggers auto-deploy)…"
	@echo "  Ensure railway.json is committed and Railway is linked to this repo."
	@echo "  Run: railway up   (or just push — Railway deploys on every push)"

push:
	git -C $(ROOT_DIR) push origin HEAD
	git -C $(ROOT_DIR) push personal HEAD

# ─────────────────────────────────────────────────────────────────────────────
# CLI & Secrets
# ─────────────────────────────────────────────────────────────────────────────

install-rail:
	@echo "→ Installing 'rail' CLI in editable mode…"
	$(PYTHON) -m pip install -e $(ROOT_DIR)packages/rail-py

secrets-list:
	rail secrets list

secrets-set:
	@if [ -z "$(KEY)" ] || [ -z "$(VAL)" ]; then \
		echo "Usage: make secrets-set KEY=NAME VAL=VALUE"; \
		exit 1; \
	fi
	rail secrets set $(KEY) $(VAL)


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

clean: kill-all
	rm -f $(ENG_DIR)/cache/*.json
	rm -f $(ENG_DIR)/ontology/onto.db $(ENG_DIR)/ontology/onto.db-journal
	rm -f $(ENG_DIR)/ontology/populated_ontology.owl
	rm -f $(ENG_DIR)/graph.html $(ENG_DIR)/graph_full.html
	@echo "  Clean complete."
