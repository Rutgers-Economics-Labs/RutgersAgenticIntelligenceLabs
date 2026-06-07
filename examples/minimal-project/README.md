# Minimal RAIL Project

This is a tiny public fixture for local-mode development and documentation. It is intentionally small and synthetic.

```bash
export RAIL_LOCAL=1
export RAIL_PATH=./examples/minimal-project
python - <<'PY'
import rail
project = rail.local("./examples/minimal-project")
print(project.slug)
PY
```

Use this project for manifest smoke tests, docs examples, and MCP client setup. It does not ship a hydrated ontology database; run a hydration pipeline before using ontology or SQL query commands.
