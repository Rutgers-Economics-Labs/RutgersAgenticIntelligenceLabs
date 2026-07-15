.PHONY: help setup install install-api install-web api web start run doctor test build clean

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
API := $(ROOT)packages/api
WEB := $(ROOT)apps/web

-include .env
export

help:
	@echo "RAIL / KRAIL local platform"
	@echo "  make setup    First-time setup (dependencies + local config)"
	@echo "  make start    Start RAIL at http://127.0.0.1:3000"
	@echo "  make doctor   Check the local toolchain and locked KRAIL version"
	@echo "  make test     Run the supported backend contract suite"
	@echo "  make build    Compile API and create a production web build"

setup: install
	@test -f .env || cp .env.example .env
	@echo "RAIL is ready. Run: make start"

install: install-api install-web

install-api:
	uv sync --project $(API) --locked

install-web:
	cd $(WEB) && npm ci

api:
	cd $(API) && uv run uvicorn app.main_krail:app --host 127.0.0.1 --port 8000 --reload

web:
	cd $(WEB) && npm run dev

start: run

run:
	@trap 'kill 0' EXIT INT TERM; $(MAKE) api & $(MAKE) web & wait

doctor:
	@command -v uv >/dev/null && echo "✓ uv" || (echo "✗ uv is required" && exit 1)
	@command -v node >/dev/null && echo "✓ node $$(node --version)" || (echo "✗ Node.js is required" && exit 1)
	@command -v git >/dev/null && echo "✓ git $$(git --version | cut -d' ' -f3)" || (echo "✗ Git is required" && exit 1)
	@uv run --project $(API) krail --version

test:
	uv run --project $(API) pytest -q $(API)/tests

build:
	uv run --project $(API) python -m compileall -q $(API)/app
	cd $(WEB) && npm run build

clean:
	rm -rf $(WEB)/.next
