.PHONY: help install install-api install-web install-engine \
        dev api web \
        hydrate hydrate-pipeline hydrate-academic \
        kill kill-api kill-web \
        convex-deploy convex-dev \
        seed \
        test \
        deploy-web deploy-api \
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
WEB_DIR  := $(ROOT_DIR)packages/web
ENG_DIR  := $(ROOT_DIR)packages/engine

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
	@echo "  RAIL Platform — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    (optional) python3 -m venv .venv   — Makefile uses .venv when present"
	@echo "    make install          Install all dependencies (api + web + engine)"
	@echo "    make install-api      Install FastAPI service deps"
	@echo "    make install-web      Install Next.js deps"
	@echo "    make install-engine   Install Streamlit/engine deps"
	@echo ""
	@echo "  Development"
	@echo "    make dev              API + Web in one terminal (Ctrl+C / SIGHUP stops both)"
	@echo "    make api              Start FastAPI only (foreground)"
	@echo "    make web              Start Next.js only (foreground)"
	@echo "    make kill             Kill both servers"
	@echo "    make kill-api         Kill FastAPI on port $(API_PORT)"
	@echo "    make kill-web         Kill Next.js on $(WEB_PORT) and :3000"
	@echo ""
	@echo "  Ontology"
	@echo "    make hydrate          Run default pipeline (nj_hydration)"
	@echo "    make hydrate-academic Academic ontology (CSV demo → academic.db / academic_populated.owl)"
	@echo "    make hydrate-pipeline PIPELINE=path/to/pipeline.yaml"
	@echo "    make seed             Seed Convex with engine default YAML configs"
	@echo "    make cache-clear      Delete cached API responses"
	@echo ""
	@echo "  Convex"
	@echo "    make convex-deploy    Push schema + functions to production"
	@echo "    make convex-dev       Run Convex dev watcher"
	@echo ""
	@echo "  Testing"
	@echo "    make test             Run all Python tests (API + engine)"
	@echo ""
	@echo "  Deploy"
	@echo "    make deploy-web       Deploy Next.js to Vercel (production)"
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

install: install-api install-web install-engine

install-api:
	@echo "→ Installing FastAPI deps…"
	$(PYTHON) -m pip install fastapi "uvicorn[standard]" httpx "pydantic>=2.7" \
	  pydantic-settings pyyaml owlready2 "pandas>=2.2" requests openpyxl

install-web:
	@echo "→ Installing Next.js deps…"
	cd $(WEB_DIR) && npm install

install-engine:
	@echo "→ Installing engine deps…"
	$(PYTHON) -m pip install owlready2 pandas streamlit pyvis requests openpyxl rdflib pyyaml

# ─────────────────────────────────────────────────────────────────────────────
# Development servers
# ─────────────────────────────────────────────────────────────────────────────

# Foreground session: bash waits on both children; no disown. Ctrl+C / SIGHUP runs cleanup.
# Uvicorn --reload and next-server are under extra PIDs — cleanup kills $! roots then matches cmdlines (see pkill -f patterns).
dev: kill
	@echo "→ API :$(API_PORT) + Web :$(WEB_PORT) — output below; Ctrl+C or close this terminal to stop both."
	@bash -c '\
	cleanup() { \
	  kill -TERM $$API_PID $$WEB_PID 2>/dev/null; \
	  sleep 0.45; \
	  kill -KILL $$API_PID $$WEB_PID 2>/dev/null; \
	  pkill -KILL -f "[u]vicorn app.main:app --port $(API_PORT)" 2>/dev/null || true; \
	  pkill -KILL -f "[n]ext dev --port $(WEB_PORT)" 2>/dev/null || true; \
	  wait $$API_PID $$WEB_PID 2>/dev/null || true; \
	}; \
	trap '\''cleanup; exit 0'\'' INT TERM HUP; \
	API_PID=; WEB_PID=; \
	cd "$(API_DIR)" && $(api_env) $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload & \
	API_PID=$$!; \
	cd "$(WEB_DIR)" && npm run dev -- --port $(WEB_PORT) & \
	WEB_PID=$$!; \
	echo ""; \
	echo "  API      → http://localhost:$(API_PORT)"; \
	echo "  API docs → http://localhost:$(API_PORT)/docs"; \
	echo "  Web      → http://localhost:$(WEB_PORT)"; \
	echo ""; \
	wait -n; st=$$?; \
	cleanup; \
	exit $$st'

api:
	@echo "→ Starting FastAPI on :$(API_PORT)…"
	cd $(API_DIR) && $(api_env) \
	  $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload

web:
	@echo "→ Starting Next.js on :$(WEB_PORT)…"
	cd $(WEB_DIR) && npm run dev -- --port $(WEB_PORT)

kill: kill-api kill-web

kill-api:
	@lsof -ti :$(API_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  API on :$(API_PORT) killed." || echo "  Nothing on :$(API_PORT)."

kill-web:
	@for port in $$(echo "$(WEB_PORT) 3000" | tr ' ' '\n' | sort -un); do \
	  if PIDS=$$(lsof -ti :$$port 2>/dev/null); [ -n "$$PIDS" ]; then \
	    kill -9 $$PIDS 2>/dev/null && echo "  Web on :$$port killed."; \
	  else \
	    echo "  Nothing on :$$port."; \
	  fi; \
	done

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

deploy-web:
	@echo "→ Deploying Next.js to Vercel…"
	cd $(WEB_DIR) && npx vercel --prod

deploy-api:
	@echo "→ Deploying API to Railway (push triggers auto-deploy)…"
	@echo "  Ensure railway.json is committed and Railway is linked to this repo."
	@echo "  Run: railway up   (or just push — Railway deploys on every push)"

# ─────────────────────────────────────────────────────────────────────────────
# Convex
# ─────────────────────────────────────────────────────────────────────────────

convex-deploy:
	@echo "→ Deploying Convex schema + functions…"
	cd $(WEB_DIR) && CONVEX_DEPLOY_KEY="$(CONVEX_DEPLOY_KEY)" npx convex deploy --yes

convex-dev:
	cd $(WEB_DIR) && CONVEX_DEPLOY_KEY="$(CONVEX_DEPLOY_KEY)" npx convex dev

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
