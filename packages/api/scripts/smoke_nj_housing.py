"""End-to-end smoke test against the NJ housing project.

Generates a real WorkOrder, dispatches via a real claude_code runner with
the project workspace as cwd, waits for session_result.json to land, and
runs the certification harness.

This is the integration test the unit tests cannot do — it exercises the
actual subprocess, the actual prompt, the actual file emissions.
"""
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path("/Users/akashdubey/Documents/CodingProjects/RAIL/RutgersAgenticIntelligenceLabs/docs/validation/nj-housing-affordability")

assert PROJECT_ROOT.is_dir(), f"project root missing: {PROJECT_ROOT}"

from app.runners.work_order_generator import generate_work_order, write_work_order
from app.runners.claude_code import ClaudeCodeRunner
from app.runners.base import TaskPayload
from app.runners.contracts import SessionResult
from tests.runner_certification.harness import certify_session_result
from app.services import session_files

SESSION_ID = "smoke-nj-001"

async def main():
    # 1. Generate the WO for a small task
    task = {
        "_id": "task-smoke-001",
        "title": "Write a one-line project summary",
        "description": "Smoke test: read README.md, write a one-line summary to topics/data/smoke_summary.md",
        "agentRole": "data",
        "repoPaths": ["topics/", "research_plan/"],
    }
    wo = generate_work_order(
        session_id=SESSION_ID,
        project_slug="nj-housing-affordability",
        role="data",
        task_id="task-smoke-001",
        task=task,
        allowed_paths=["topics/", "research_plan/"],
        runner_name="claude_code",
    )
    print(f"[1/6] WO generated: {wo.work_order_id}  task_type={wo.task_type.value}")
    print(f"      capabilities: {[c.value for c in wo.capabilities_required]}")

    # 2. Write WO to project on disk (audit-trail copy)
    wo_path = write_work_order(wo, workspace_root=PROJECT_ROOT, project_root=PROJECT_ROOT)
    print(f"[2/6] WO written: {wo_path.relative_to(PROJECT_ROOT)}")

    # 3. Ensure session directory exists where the runner will write its result
    sess_dir = PROJECT_ROOT / "research_plan" / "sessions" / "smoke" / SESSION_ID
    sess_dir.mkdir(parents=True, exist_ok=True)
    
    # 4. Build a TaskPayload — what session_lifecycle would normally construct
    payload = TaskPayload(
        project_slug="nj-housing-affordability",
        role="data",
        task_id="task-smoke-001",
        repo_url="",
        branch="main",
        local_repo_path=str(PROJECT_ROOT),
        task_description=task["description"],
        allowed_paths=["topics/", "research_plan/"],
        acceptance_criteria=[
            "writes topics/data/smoke_summary.md with one sentence",
            "emits research_plan/sessions/smoke/" + SESSION_ID + "/session_result.json",
        ],
        session_root=str(sess_dir),
        work_order_id=wo.work_order_id,
        work_order_path=f"research_plan/work_orders/{wo.work_order_id}.json",
        session_result_path=f"research_plan/sessions/smoke/{SESSION_ID}/session_result.json",
    )

    # 5. Construct an explicit prompt that asks the runner to emit session_result.json.
    # In production session_lifecycle builds this; for smoke we inline it.
    prompt = f"""Smoke test work order. Read the work order at {payload.work_order_path}, do the small task described below, then write a structured session result.

Task: {task['description']}

WHEN DONE, you MUST write `{payload.session_result_path}` containing valid JSON matching this schema:
{{
  "session_id": "{SESSION_ID}",
  "work_order_id": "{wo.work_order_id}",
  "status": "completed",
  "summary": "<one-sentence summary of what you did>",
  "task_type": "{wo.task_type.value}",
  "runner_name": "claude_code",
  "files_changed": ["topics/data/smoke_summary.md"]
}}

Do not skip writing session_result.json — the harness validates it."""

    print(f"[3/6] Dispatching to claude_code (cwd={PROJECT_ROOT})...")
    runner = ClaudeCodeRunner(command="claude")
    
    # Override TaskPayload's task_description so the prompt builder picks up our richer instructions
    payload.task_description = prompt
    
    session = await runner.create_session(payload)
    convex_id = session.get("convex_session_id") or session.get("session_id")
    print(f"      session id: {convex_id}  status: {session.get('status')}")

    # 6. Poll for completion
    import time
    start = time.time()
    timeout = 180  # 3 min for a small claude task
    last_status = None
    while time.time() - start < timeout:
        await asyncio.sleep(5)
        try:
            info = await runner.get_session(convex_id)
            st = info.get("status")
            if st != last_status:
                print(f"      [{int(time.time() - start)}s] status={st}")
                last_status = st
            if st in {"completed", "failed", "cancelled"}:
                break
        except Exception as e:
            print(f"      poll error: {e}")
            break

    print(f"[4/6] Runner finished in {int(time.time() - start)}s (final status: {last_status})")

    # 7. Look for the session_result.json
    candidates = [
        PROJECT_ROOT / payload.session_result_path,
        sess_dir / "session_result.json",
    ]
    result_path = next((p for p in candidates if p.is_file()), None)
    if not result_path:
        print(f"[5/6] ❌ session_result.json NOT found in any of:")
        for p in candidates:
            print(f"        {p}")
        print(f"[6/6] CERTIFICATION SKIPPED (no result file)")
        return 1

    print(f"[5/6] session_result.json at {result_path.relative_to(PROJECT_ROOT)}")

    # 8. Certify
    outcome = certify_session_result(result_path, work_order=wo)
    print(f"[6/6] certification: passed={outcome.passed}")
    if outcome.issues:
        for issue in outcome.issues:
            print(f"        - {issue}")
    if outcome.parsed:
        p = outcome.parsed
        print(f"      parsed: status={p.status.value} runner={p.runner_name} summary={(p.summary or '')[:80]!r}")

    return 0 if outcome.passed else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
