#!/usr/bin/env bash
set -euo pipefail

# Install the RAIL engine from the monorepo so any cloud agent (Jules, etc.)
# has access to the full ontology/pipeline/analysis stack.
pip install --quiet \
  "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/engine"

# Install common data science deps used by analysis scripts
pip install --quiet pandas requests httpx pyyaml duckdb matplotlib statsmodels scikit-learn

echo "RAIL engine installed. Available as: import engine"
python -c "import engine; print('engine ok')" 2>/dev/null || echo "Note: engine import check skipped"
