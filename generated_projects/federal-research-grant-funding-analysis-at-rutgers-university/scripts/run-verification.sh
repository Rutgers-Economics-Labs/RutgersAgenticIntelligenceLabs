#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/packages/api/.venv/bin/python}"

"${PYTHON_BIN}" "${ROOT}/scripts/build_research_artifacts.py"
"${PYTHON_BIN}" "${ROOT}/scripts/verify_project_state.py"
