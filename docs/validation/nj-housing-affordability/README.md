# NJ Housing Affordability and Labor Market Study

Validation archetype: **time-series econ** (FRED hydrate → DuckDB → grounded research → expansion tasks).

## Live E2E runbook (Sprint 2–3)

### Prerequisites

| Requirement | Notes |
|-------------|--------|
| `GOOGLE_API_KEY` | Gemini planner + research (`run_live_agent_loop.py`) |
| `FRED_API_KEY` | Real FRED HTTP hydrate in phase 5 |
| `CONVEX_URL` / deploy key | Required for API + autopilot worker path |
| RAIL API | `http://localhost:8000` — optional for the script-only path |

### Quick path (no API)

From `packages/api/`:

```bash
python scripts/run_live_agent_loop.py --full-e2e
```

Exercises all five worker roles (planner, data, research, coding, artifact), persists grounded claims to `research_plan/state/claims.json`, writes `artifacts/dashboard.html`, and completes expansion tasks for real closeout (no `--defer-expansion`).

For a Sprint 2 closeout demo only (expansion tasks cancelled, not completed):

```bash
python scripts/run_live_agent_loop.py --defer-expansion
```

**Expected closeout:** without `--full-e2e` or `--defer-expansion`, `closeout` may show `blocked` with `N non-terminal task(s) remain` until expansion tasks are completed — correct fail-closed behavior.

Results summary: `docs/validation/live_agent_loop_summary.json`

### Full path (API + Convex + autopilot)

1. Start API (from `packages/api`): `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
2. Register this checkout in Convex:

   ```bash
   python scripts/register_validation_project.py
   ```

3. Smoke-test control plane:

   ```bash
   curl -s http://127.0.0.1:8000/api/v1/projects/nj-housing-affordability/reality | python -m json.tool
   curl -s -X POST http://127.0.0.1:8000/api/v1/projects/nj-housing-affordability/command-center/reconcile
   ```

4. Set `FRED_API_KEY` in project secrets vault (if not already in `.env`)
5. Run live loop with Convex promotion: `python scripts/run_live_agent_loop.py --full-e2e` (hydrate phase calls `attach_local_hydration_to_convex` when registered)
6. Bounded autopilot ticks: `python scripts/run_autopilot_tick.py --slug nj-housing-affordability --iterations 10`
7. Or start autopilot: `POST /api/v1/projects/nj-housing-affordability/autopilot` with `{"autoApprove": false}`
8. Poll `GET /api/v1/projects/nj-housing-affordability/autopilot/status` until closeout is `ready`

### Verification

```bash
./scripts/run-verification.sh
python scripts/verify_project_state.py
```

### Blockers observed (2026-05-19)

- Closeout blocks while expansion follow-up tasks remain `ready` unless you use `--full-e2e` or `--defer-expansion`
- After multiple live-loop runs, ontology auditor may block until hydration state is refreshed (re-run with registered project or `register_validation_project.py`)
