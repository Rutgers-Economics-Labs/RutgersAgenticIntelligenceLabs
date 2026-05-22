# Live End-to-End Smoke Test — NJ Housing

**Branch:** `spec/runner-protocol-phase-0`
**Date:** 2026-05-22
**Project under test:** `docs/validation/nj-housing-affordability`
**Runner under test:** `claude_code` (claude CLI v2.1.148)
**Script:** `packages/api/scripts/smoke_nj_housing.py`

## What this validates

The first **real** end-to-end exercise of the Phase 2–5 runner protocol against a real project with a real CLI subprocess. Until this, all green tests were either unit tests (synthetic fixtures) or contract-level (in-memory, no subprocess).

Specifically, this proves the following path actually executes:

```
generate_work_order()
  → write_work_order(project_root)
  → TaskPayload built with WO id + WO path + session_result path
  → ClaudeCodeRunner.create_session(payload)  ← real subprocess
  → claude CLI runs, reads project files, writes artifact
  → claude writes session_result.json at the path declared in the WO
  → certify_session_result(path, work_order=wo) returns passed=True
```

## Result

```
[1/6] WO generated: wo_9264644440f9  task_type=data_ingestion
      capabilities: ['edit_files', 'fetch_remote_data']
[2/6] WO written: research_plan/work_orders/wo_9264644440f9.json
[3/6] Dispatching to claude_code (cwd=.../nj-housing-affordability)...
      session id: claude_code_b547ba94e747  status: running
[4/6] Runner finished
[5/6] session_result.json at research_plan/sessions/smoke/smoke-nj-001/session_result.json
[6/6] certification: passed=True
      parsed: status=completed runner=claude_code summary='Read README.md and wrote a one-line summary...'
```

## Artifacts written during this run

All three files exist on disk in the NJ housing project tree:

| File | What it proves |
|---|---|
| `research_plan/work_orders/wo_9264644440f9.json` | The typed WorkOrder is persisted with all Phase 0 fields (capabilities_required, allowed_paths, idempotency_key, input_hash, trust_policy, expected_progress) |
| `research_plan/sessions/smoke/smoke-nj-001/session_result.json` | claude_code emitted a structurally valid SessionResult — work_order_id matches WO, task_type matches, runner_name set |
| `topics/data/smoke_summary.md` | The actual artifact claude_code produced. Real file written to disk by a real CLI subprocess. |

The contents of `session_result.json` (verbatim):

```json
{
  "session_id": "smoke-nj-001",
  "work_order_id": "wo_9264644440f9",
  "status": "completed",
  "summary": "Read README.md and wrote a one-line summary identifying the project as the NJ Housing Affordability and Labor Market Study to topics/data/smoke_summary.md.",
  "task_type": "data_ingestion",
  "runner_name": "claude_code",
  "files_changed": ["topics/data/smoke_summary.md"]
}
```

## What this does NOT yet validate

I want to be specific about the gaps this single smoke test does *not* close. These are the next things to test before declaring the platform integration-complete:

1. **Session lifecycle finalization.** The smoke script bypasses `session_lifecycle._finalize_workspace_review`. In production, that function reads `session_result.json`, runs certification, applies loop closure (claims/sources update), and writes the post-run audit. None of that ran here. **The next smoke test should go through `create_runner_session` so finalization fires.**
2. **Status reporting from runner back to operator.** During the run, polling `runner.get_session(id).status` continued to return `"queued"` even after the subprocess finished and wrote files. The status state machine inside `ClaudeCodeRunner` / `LocalCLIRunner` is not advancing on completion when bypassing the normal lifecycle. Worth investigating before the UI inspector depends on this signal.
3. **Capability router dispatch.** The smoke script hard-coded `runner_name="claude_code"`. The capability router was not invoked, no dispatch_log was written. **Add a smoke variant that calls `route_task()` first and asserts a dispatch_log lands.**
4. **MCP injection — partially validated.** `ClaudeCodeRunner.create_session()` auto-wrote a `.mcp.json` into the project root pointing at the `rail-mcp` server with the right `RAIL_PROJECT`, `RAIL_SESSION_ID`, and `RAIL_WORK_ORDER_ID` env vars. So the injection step works. What remains untested: that the runner actually loads MCP, calls `rail.ask`, and the tier-3 escalation lands in an operator inbox. **Next smoke test should include a prompt that forces the runner to ask a question.**
5. **Loop closure into claims/sources.** Because `_finalize_workspace_review` didn't run, `research_plan/state/claims.json` was not updated from the session's `claims[]`. **Next smoke test should include claims in the SessionResult and assert they end up in the project state.**
6. **Autopilot drive.** The smoke script dispatched manually. The full path — planner schedules a task, autopilot picks it up, runner runs, session promotes — has not been exercised end-to-end.

In other words: the *contract spine* works in the wild. The *control plane* around it (finalization, lifecycle, autopilot, loop closure) still needs its own smoke pass.

## Real bugs uncovered during this run

### 1. `rail-mcp` server binary is not installed — **FIXED 2026-05-22**

Earlier the auto-written `.mcp.json` referenced a `rail-mcp` command that wasn't installed:

```
MCP server "rail": Connection failed after 16ms: Executable not found in $PATH: "rail-mcp"
```

Two fixes shipped on `feat/kill-switch-and-followups`:

1. `make install-mcp` now pip-installs `packages/mcp-server` editable, so the `rail-mcp` entry point lands on PATH.  `make install` includes it.
2. `app/runners/mcp_injector.py` now falls back to `python -m rail_mcp.server` using `sys.executable` when `rail-mcp` isn't on PATH — so the platform works even if the operator skips the install step.

Re-running the smoke test confirms:

```
MCP server "rail": Successfully connected (transport: stdio) in 417ms
MCP server "rail": Connection established with capabilities:
  {"hasTools":true,"hasPrompts":true,"hasResources":true,
   "serverVersion":{"name":"RAIL Platform","version":"1.9.4"}}
```

Phase 4 Q&A is now genuinely live against real CLIs — `rail.ask`, `rail.list_project_state`, `rail.get_work_order`, `rail.submit_session_result` are all exposed to runners during a session.

### 2. `ClaudeCodeRunner.get_session()` returns `status="queued"` indefinitely

When the runner is invoked outside the normal session_lifecycle path, the in-memory session state never advances even after the subprocess finishes and writes files. Root cause hypothesis: the status updater is wired into the lifecycle hook, not the runner itself. Worth a follow-up issue. Not blocking but should be tracked.

## How to re-run

```bash
cd packages/api
PYTHONPATH=. python scripts/smoke_nj_housing.py
```

The script is intentionally self-contained (no Convex dependency, no fixtures). It will:

1. Write a new WO into the NJ housing project (`research_plan/work_orders/`)
2. Launch a real `claude` subprocess in that project's cwd
3. Wait up to 3 minutes for the runner to finish
4. Look for `session_result.json` at the path declared in the WO
5. Run the certification harness and exit 0/1

**Cost note:** this calls a real claude API and pays for a small ~5-10 token job. Don't loop it in CI.
