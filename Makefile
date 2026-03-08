.PHONY: help install hydrate app kill clean cache-clear

PYTHON   := $(shell which python)
PIPELINE := configs/pipelines/nj_hydration.yaml
PORT     := 8501

help:
	@echo "Usage:"
	@echo "  make install      Install Python dependencies"
	@echo "  make hydrate      Run the ontology hydration pipeline"
	@echo "  make app          Start the Streamlit explorer"
	@echo "  make kill         Kill the running Streamlit server"
	@echo "  make cache-clear  Delete cached API responses"
	@echo "  make clean        Delete generated ontology files + cache"
	@echo "  make all          hydrate + app"

install:
	$(PYTHON) -m pip install owlready2 pandas streamlit pyvis requests openpyxl rdflib pyyaml

hydrate:
	$(PYTHON) hydrate.py --pipeline $(PIPELINE)

app:
	$(PYTHON) -m streamlit run app.py --server.port $(PORT)

kill:
	@lsof -ti :$(PORT) | xargs kill -9 2>/dev/null && echo "Streamlit on :$(PORT) killed." || echo "Nothing running on :$(PORT)."

cache-clear:
	rm -f cache/*.json
	@echo "Cache cleared."

clean: kill
	rm -f cache/*.json
	rm -f ontology/onto.db ontology/onto.db-journal ontology/populated_ontology.owl
	rm -f graph.html graph_full.html
	@echo "Clean complete."

all: hydrate app
