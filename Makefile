.PHONY: help install install-api install-web api web run test build clean

ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
API := $(ROOT)packages/api
WEB := $(ROOT)apps/web

-include .env
export

help:
	@echo "RAIL / KRAIL local platform"
	@echo "  make install  Install locked API and web dependencies"
	@echo "  make run      Start API :8000 and web :3000"
	@echo "  make test     Run the supported backend contract suite"
	@echo "  make build    Compile API and create a production web build"

install: install-api install-web

install-api:
	uv sync --project $(API) --locked

install-web:
	cd $(WEB) && npm ci

api:
	cd $(API) && uv run uvicorn app.main_krail:app --host 127.0.0.1 --port 8000 --reload

web:
	cd $(WEB) && npm run dev

run:
	@trap 'kill 0' EXIT INT TERM; $(MAKE) api & $(MAKE) web & wait

test:
	uv run --project $(API) pytest -q $(API)/tests

build:
	uv run --project $(API) python -m compileall -q $(API)/app
	cd $(WEB) && npm run build

clean:
	rm -rf $(WEB)/.next
