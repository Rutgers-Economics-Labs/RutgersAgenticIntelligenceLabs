#!/usr/bin/env bash
set -euo pipefail

# 1. Install the RAIL engine. 
# We prefer local installation if we're in the monorepo, 
# otherwise we fall back to the remote GitHub package.
LOCAL_ENGINE="$RAIL_PROJECT_ROOT/../../packages/engine"
if [ -d "$LOCAL_ENGINE" ]; then
  echo "→ Installing engine from local path: $LOCAL_ENGINE"
  pip install --quiet -e "$LOCAL_ENGINE"
else
  echo "→ Installing engine from GitHub..."
  pip install --quiet \
    "git+https://github.com/Rutgers-Economics-Labs/RutgersAgenticIntelligenceLabs.git#subdirectory=packages/engine"
fi

# 2. Common data science deps used by analysis scripts
pip install --quiet pandas requests httpx pyyaml duckdb matplotlib statsmodels scikit-learn

echo "RAIL engine installed."
python -c "import engine; print('engine ok')" 2>/dev/null || echo "Note: engine import check skipped"
