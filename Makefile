.PHONY: help install install-api install-web install-engine \
        dev api web \
        hydrate hydrate-pipeline \
        kill kill-api kill-web \
        convex-deploy convex-dev \
        seed \
        clean cache-clear \
        push

ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
PYTHON   := python3
API_DIR  := $(ROOT_DIR)packages/api
WEB_DIR  := $(ROOT_DIR)packages/web
ENG_DIR  := $(ROOT_DIR)packages/engine

API_PORT := 8000
WEB_PORT := 3000
PIPELINE := configs/pipelines/nj_hydration.yaml

# ── Env vars forwarded to the API server ─────────────────────────────────────
# Copy .env.example → .env and fill in values, or export them before running.
-include .env
export

# ─────────────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  RAIL Platform — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    make install          Install all dependencies (api + web + engine)"
	@echo "    make install-api      Install FastAPI service deps"
	@echo "    make install-web      Install Next.js deps"
	@echo "    make install-engine   Install Streamlit/engine deps"
	@echo ""
	@echo "  Development"
	@echo "    make dev              Start API (port $(API_PORT)) + Web (port $(WEB_PORT)) in background"
	@echo "    make api              Start FastAPI server only (foreground)"
	@echo "    make web              Start Next.js dev server only (foreground)"
	@echo "    make kill             Kill both servers"
	@echo "    make kill-api         Kill FastAPI on port $(API_PORT)"
	@echo "    make kill-web         Kill Next.js on port $(WEB_PORT)"
	@echo ""
	@echo "  Ontology"
	@echo "    make hydrate          Run default pipeline (nj_hydration)"
	@echo "    make hydrate-pipeline PIPELINE=path/to/pipeline.yaml"
	@echo "    make seed             Seed Convex with engine default YAML configs"
	@echo "    make cache-clear      Delete cached API responses"
	@echo ""
	@echo "  Convex"
	@echo "    make convex-deploy    Push schema + functions to production"
	@echo "    make convex-dev       Run Convex dev watcher"
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

dev: kill
	@echo "→ Starting API on :$(API_PORT) and Web on :$(WEB_PORT)…"
	@cd $(API_DIR) && CONVEX_URL=$(CONVEX_URL) ENGINE_ROOT=../engine \
	  $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload \
	  > /tmp/rail-api.log 2>&1 & echo "  API pid $$!"
	@cd $(WEB_DIR) && npm run dev -- --port $(WEB_PORT) \
	  > /tmp/rail-web.log 2>&1 & echo "  Web pid $$!"
	@sleep 3
	@echo ""
	@echo "  API   → http://localhost:$(API_PORT)"
	@echo "  API docs → http://localhost:$(API_PORT)/docs"
	@echo "  Web   → http://localhost:$(WEB_PORT)"
	@echo ""
	@echo "  Logs: tail -f /tmp/rail-api.log  |  tail -f /tmp/rail-web.log"

api:
	@echo "→ Starting FastAPI on :$(API_PORT)…"
	cd $(API_DIR) && CONVEX_URL=$(CONVEX_URL) ENGINE_ROOT=../engine \
	  $(PYTHON) -m uvicorn app.main:app --port $(API_PORT) --reload

web:
	@echo "→ Starting Next.js on :$(WEB_PORT)…"
	cd $(WEB_DIR) && npm run dev -- --port $(WEB_PORT)

kill: kill-api kill-web

kill-api:
	@lsof -ti :$(API_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  API on :$(API_PORT) killed." || echo "  Nothing on :$(API_PORT)."

kill-web:
	@lsof -ti :$(WEB_PORT) | xargs kill -9 2>/dev/null \
	  && echo "  Web on :$(WEB_PORT) killed." || echo "  Nothing on :$(WEB_PORT)."

# ─────────────────────────────────────────────────────────────────────────────
# Ontology hydration
# ─────────────────────────────────────────────────────────────────────────────

hydrate:
	@echo "→ Running pipeline: $(ENG_DIR)/$(PIPELINE)"
	cd $(ENG_DIR) && $(PYTHON) hydrate.py --pipeline $(PIPELINE)

hydrate-pipeline:
	cd $(ENG_DIR) && $(PYTHON) hydrate.py --pipeline $(PIPELINE)

seed:
	@echo "→ Seeding Convex with default YAML configs…"
	$(PYTHON) scripts/seed_convex.py

cache-clear:
	rm -f $(ENG_DIR)/cache/*.json
	@echo "  Cache cleared."

# ─────────────────────────────────────────────────────────────────────────────
# Convex
# ─────────────────────────────────────────────────────────────────────────────

convex-deploy:
	@echo "→ Deploying Convex schema + functions…"
	cd $(WEB_DIR) && npx convex deploy --yes

convex-dev:
	cd $(WEB_DIR) && npx convex dev

# ─────────────────────────────────────────────────────────────────────────────
# Git
# ─────────────────────────────────────────────────────────────────────────────

push:
	git push origin HEAD
	git push personal HEAD

# ─────────────────────────────────────────────────────────────────────────────
# Cleanup
# ─────────────────────────────────────────────────────────────────────────────

clean: kill
	rm -f $(ENG_DIR)/cache/*.json
	rm -f $(ENG_DIR)/ontology/onto.db $(ENG_DIR)/ontology/onto.db-journal
	rm -f $(ENG_DIR)/ontology/populated_ontology.owl
	rm -f $(ENG_DIR)/graph.html $(ENG_DIR)/graph_full.html
	rm -f /tmp/rail-api.log /tmp/rail-web.log
	@echo "  Clean complete."
