# Handoff: Runner Protocol Phase 1 (in progress)

Date: 2026-05-21
From: previous Claude Code session (about to hit context limit)
Branch: `spec/runner-protocol-phase-0`
Working directory: `/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs`

## TL;DR

I am mid-way through **Phase 1** of `docs/future-spec-runner-protocol.md`.
Phase 0 (contracts + certification harness) is done and committed
(`e0cd930`). Phase 1 deliverables are partially on disk but **not yet
committed**. Next agent: finish Phase 1, commit, push, then continue to
Phase 2.

## State on disk RIGHT NOW (uncommitted)

```
M  packages/api/app/routers/runners.py
   (extended GET /runners + added GET /runners/{name}/probe)
M  packages/api/app/runners/contracts/runner_profile.py
   (promoted supports_streaming + supports_native_questions to CapabilityState
   from bool — three-valued logic matches the rest of the schema)
M  packages/api/tests/runner_certification/test_contracts.py
   (updated to match the schema change above)
?? packages/api/app/runners/probe.py
?? packages/api/app/runners/profile_loader.py
?? packages/api/app/runners/profiles/
   (six YAMLs: jules, claude_code, codex_cli, gemini_cli, cursor_cli, copilot_cli)
?? packages/api/tests/runner_certification/test_profiles.py
?? docs/diag-verification-stuck-pending.md
   (the diagnostic from the parallel agent — already actioned in commit 18824cf, can be committed any time)
?? docs/handoff-runner-protocol-phase-1.md
   (this file)
```

**Status: 37/37 tests passing in `tests/runner_certification/`.**
Schema bug caught and fixed before handoff — `supports_streaming` and
`supports_native_questions` were typed `bool` in the schema but several
YAMLs needed `"configurable"` (Cursor's streaming depends on mode;
Codex/Gemini/Cursor Q&A support depends on operator MCP config). Both
fields are now `CapabilityState`. If the next agent needs to make a
similar binary-vs-three-valued judgment for a NEW execution field,
prefer `CapabilityState` whenever operator setup can change the answer.

Do **not** lose these files. They are about 80% of Phase 1.

## Branch stack

```
yaml-driven-hydration                       (main)
  └─ spec/background-health-governance       (spec doc only)
      └─ fix/research-not-blocked-by-health  (3 commits — pushed)
          └─ spec/runner-protocol-phase-0    ← you are here, has 1 commit pushed (e0cd930)
```

The uncommitted Phase 1 work sits on top of `e0cd930` on
`spec/runner-protocol-phase-0`. It should NOT branch off into a separate
`phase-1` branch — keep it stacked on this one, then push.

## What's already done (committed at e0cd930)

- `docs/future-spec-runner-protocol.md` — the full 7-phase plan
- `packages/api/app/runners/contracts/` — three Pydantic schemas
  (`WorkOrder`, `SessionResult`, `RunnerProfile`)
- `packages/api/tests/runner_certification/` — 29 tests, all passing
  (`test_contracts.py`, `test_harness.py`, `harness.py`)

Run the green suite to verify the baseline still passes:

```bash
cd packages/api
source ../../.venv/bin/activate
python -m pytest tests/runner_certification/ -q --no-header
# expected: 29 passed
```

## Phase 1 — what's on disk and what's left

Read `docs/future-spec-runner-protocol.md` § "Phase 1" for the deliverable
list. Status by deliverable:

| Deliverable | Status |
|---|---|
| Six profile YAMLs under `packages/api/app/runners/profiles/` | **DONE** (on disk, uncommitted) |
| `packages/api/app/runners/profile_loader.py` | **DONE** (on disk, uncommitted) |
| `packages/api/app/runners/probe.py` | **DONE** (on disk, uncommitted) |
| `GET /api/runners` — extended | **DONE** (router edit on disk, uncommitted) |
| `GET /api/runners/{name}/probe` | **DONE** (router edit on disk, uncommitted) |
| `tests/runner_certification/test_profiles.py` | **DONE** (on disk, uncommitted) |
| `tests/runner_certification/test_probe.py` | **NOT YET WRITTEN** |
| Tests for the extended `/runners` endpoint | **NOT YET WRITTEN** |
| Wire profile probe into operator UI panel | **DEFERRED** (separate frontend commit; out of Phase 1 scope per the spec) |

### What you need to do to finish Phase 1

1. **Run what's already on disk** to make sure nothing is broken:

   ```bash
   cd packages/api
   source ../../.venv/bin/activate
   python -m pytest tests/runner_certification/ -q --no-header
   # expected: 29 (existing) + 8 (test_profiles.py) = 37 passing
   ```

   If `test_profiles.py` fails, the failure message names the offending
   YAML. Most likely culprit if anything breaks: schema drift between the
   YAML and `runner_profile.py`.

2. **Write `tests/runner_certification/test_probe.py`** covering:

   - `probe_runner("claude_code")` returns `installed.status == "fail"` and
     `readiness == "red"` when `claude` is not on PATH. Mock `shutil.which`
     to return None.
   - `probe_runner("claude_code")` returns `installed.status == "pass"` and
     `readiness == "yellow"` when `claude` IS on PATH (mock `shutil.which`
     to return a path; mock `asyncio.create_subprocess_exec` to return a
     fake process whose `communicate()` returns `(b"1.0.0\n", b"")` and
     `returncode == 0`).
   - `probe_runner("jules")` returns red when `JULES_API_KEY` is empty,
     yellow when it's set. Use `monkeypatch.setenv` / `delenv`.
   - `probe_runner("not_a_real_runner")` returns `None`.
   - `probe_all()` returns a dict keyed by runner name.

   Pattern: most things should be `@pytest.mark.asyncio` with monkeypatched
   `shutil.which` and `asyncio.create_subprocess_exec`. Look at how
   `tests/test_session_lifecycle.py` mocks subprocess calls for the shape.

3. **Write tests for the extended `/runners` endpoint and `/runners/{name}/probe`**.
   File: `tests/runner_certification/test_runners_endpoint.py` (don't
   collide with the existing `tests/test_runners_router.py`).

   Use FastAPI's `TestClient`. Check:
   - `GET /api/v1/runners` returns 200 with a `runners: [...]` list
     containing all six expected names
   - Each row has `profile` and `probe` keys when the runner has a profile
   - `GET /api/v1/runners/claude_code/probe` returns 200 with a `runner_name`,
     `installed`, `authenticated`, `readiness`
   - `GET /api/v1/runners/not_a_real_runner/probe` returns 404

4. **Commit and push.** Suggested message:

   ```
   phase-1: runner profiles + probe system

   Six profile YAMLs declaring each runner's capabilities, certification
   level, task affinity, and execution shape. profile_loader.py loads
   them with caching; probe.py runs cheap dynamic readiness checks
   (command on PATH, version reachable, hosted credentials present).
   The existing /api/v1/runners endpoint now returns profile + probe
   alongside factory registration; new /api/v1/runners/{name}/probe
   runs a fresh probe on demand.

   Tests: tests/runner_certification/{test_profiles, test_probe,
   test_runners_endpoint}.py. Profile-set/factory-registry parity
   check fails CI loudly when someone adds a runner without a profile.

   Defers: UI panel for runner readiness matrix (separate frontend
   commit; out of Phase 1 scope per the spec).
   ```

   Then `git push`.

## What's NEXT after Phase 1 lands

**Phase 2 — Structured I/O.** See `docs/future-spec-runner-protocol.md` §
"Phase 2".

Critical thing to know before starting Phase 2: **it needs the fixes in
`fix/research-not-blocked-by-health` to test session_result emission
cleanly.** That branch is already pushed but not yet merged. Options:

- Wait for `fix/research-not-blocked-by-health` to merge to main, then
  rebase `spec/runner-protocol-phase-0` onto main
- Or merge `fix/research-not-blocked-by-health` into
  `spec/runner-protocol-phase-0` directly (less clean but unblocks Phase 2
  immediately)

I'd recommend the rebase — keeps history linear and avoids long-running
merge commits.

## Key facts the next agent should not have to rediscover

- **The factory in `packages/api/app/runners/factory.py:36-43`** registers
  six runners: `jules`, `claude_code`, `codex_cli`, `gemini_cli`,
  `cursor_cli`, `copilot_cli`. The profile YAMLs match these names exactly.
- **`gh copilot suggest`** is the default command for `copilot_cli` and it
  is a suggestion CLI, not autonomous. The profile YAML reflects this with
  `status: advisory_only` and empty `task_affinity`. A test in
  `test_profiles.py` enforces this — do not "fix" it by making Copilot
  certified.
- **Probes must not make outbound API calls.** Auth verification is
  intentionally `SKIP`, not `PASS`/`FAIL`. The spec says probes are cheap.
  If you want to add a "really verify auth" check, put it in a separate
  `certify_runner()` function that operators trigger explicitly.
- **`PROBE_SUBPROCESS_TIMEOUT_SECONDS = 3.0`**. Don't bump this without
  thinking — autopilot may probe-all on every tick.
- **`extra="forbid"` on the contract schemas is deliberate.** Schema drift
  should fail loud. If a test breaks because of a "surprise" field, the
  fix is usually to update the schema, not relax the constraint.

## Pre-existing test failures (NOT caused by this work — ignore)

These were verified pre-existing before any of this work landed:

- `tests/test_autopilot_service.py::test_autopilot_creates_ontology_lifecycle_tasks_for_not_hydrated_project`
- 8 failures in `tests/test_session_lifecycle.py::test_finalize_workspace_review_*`

Don't try to fix them as part of Phase 1. They're separate concerns.

## If the prior session's tools haven't loaded for you yet

You'll probably need to load these deferred tools to do real work:

```
ToolSearch query: "select:Read,Edit,Write,Bash,Grep,Glob,Agent,AskUserQuestion"
```

## Recovery if something is wrong

If `git status` shows files I described as "on disk" missing:

```bash
git log --all --oneline -20 | grep -i "phase-1\|profiles\|probe"
# might be in a stash
git stash list
```

If everything is missing and you're starting fresh, the spec doc at
`docs/future-spec-runner-protocol.md` § "Phase 1" has the full deliverable
list and acceptance criteria — Phase 1 is reproducible from the spec alone
in ~4-6 hours of focused work.

---

End of handoff. Good luck.
