"""Tests for Milestone 6: Post-Run Auditors — all five auditors fire after every worker run."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

RAIL_PY_ROOT = Path(__file__).parents[3] / "rail-py"
if str(RAIL_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(RAIL_PY_ROOT))


MINIMAL_MANIFEST = """\
version: 1
project:
  name: "Test"
  slug: "test"
  default_branch: "main"
paths:
  ontology_root: ".ontology"
  topics_root: "topics"
  specs_root: "specs"
  plan_root: "research_plan"
  agents_root: "agents"
  skills_root: "skills"
  artifacts_root: "artifacts"
hydration:
  ontology_file: ".ontology/ontology.yaml"
  sources_dir: ".ontology/sources"
  pipelines_dir: ".ontology/pipelines"
agents:
  roles_dir: "agents"
  default_runner: "codex_cli"
  sequential_execution: true
  planner_thread_mode: "project"
  default_planner_role: "planner"
frontend:
  topic_index_mode: "filesystem"
  artifact_index_mode: "filesystem"
"""


def _setup_project(tmp_path: Path) -> tuple[dict, Path, Path]:
    (tmp_path / "rail.yaml").write_text(MINIMAL_MANIFEST, encoding="utf-8")
    state_dir = tmp_path / "research_plan" / "state"
    state_dir.mkdir(parents=True)
    for name in ["sources.json", "claims.json", "artifact_lineage.json",
                 "verification_runs.json", "assumptions.json", "source_candidates.json",
                 "claim_candidates.json", "entity_candidates.json", "conflicts.json"]:
        (state_dir / name).write_text("[]", encoding="utf-8")

    session_root = tmp_path / "research_plan" / "sessions" / "research" / "sess-001"
    session_root.mkdir(parents=True)
    state = {"session_id": "sess-001", "status": "completed", "review_status": "review"}
    (session_root / "state.json").write_text(json.dumps(state), encoding="utf-8")

    project = {"_id": "proj1", "localRepoPath": str(tmp_path), "slug": "test"}
    return project, tmp_path, session_root


@pytest.mark.asyncio
async def test_write_post_run_audit_includes_auditors_key(tmp_path):
    from app.services.audit_service import write_post_run_audit

    project, project_root, session_root = _setup_project(tmp_path)

    mock_auditors = {
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "ready", "blockers": []},
        "ontology": {"status": "ready", "blockers": []},
        "integrity": {"status": "ready", "blockers": []},
        "closeout": {"status": "blocked", "blockers": ["1 non-terminal task(s) remain."]},
    }

    with (
        patch("app.services.audit_service.planner_service.ensure_main_board", new_callable=AsyncMock, return_value={"_id": "main"}),
        patch("app.services.audit_service.planner_service.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.auditor_service.project_reality_status", new_callable=AsyncMock, return_value={
            "staleRuntimeSessionCount": 0,
            "zombieSessionCount": 0,
            "duplicateTaskFileCount": 0,
            "taskSessionMismatchCount": 0,
            "staleAuditSessionCount": 0,
            "runningAgentStatusDriftCount": 0,
            "runningAgentRoleDriftCount": 0,
            "runningAgentRunnerDriftCount": 0,
            "secretPolicyRoleDriftCount": 0,
            "roleConfigAliasDriftCount": 0,
            "details": {},
        }),
        patch("app.services.auditor_service.build_auditor_statuses", new_callable=AsyncMock, return_value=mock_auditors),
    ):
        result = await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-001",
            session={"role": "research"},
            changed_files=["research_plan/data.md"],
        )

    assert "auditors" in result["payload"]
    auditors = result["payload"]["auditors"]
    assert "session" in auditors
    assert "planner" in auditors
    assert "ontology" in auditors
    assert "integrity" in auditors
    assert "closeout" in auditors


@pytest.mark.asyncio
async def test_write_post_run_audit_auditors_key_empty_dict_on_failure(tmp_path):
    """Auditor failure must not crash the audit write — auditors key is empty dict."""
    from app.services.audit_service import write_post_run_audit

    project, project_root, session_root = _setup_project(tmp_path)

    with (
        patch("app.services.audit_service.planner_service.ensure_main_board", new_callable=AsyncMock, return_value={"_id": "main"}),
        patch("app.services.audit_service.planner_service.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.auditor_service.build_auditor_statuses", new_callable=AsyncMock, side_effect=RuntimeError("DB down")),
    ):
        result = await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-002",
            session={"role": "research"},
            changed_files=[],
        )

    assert result["payload"]["auditors"] == {}


@pytest.mark.asyncio
async def test_write_post_run_audit_persists_auditors_to_json(tmp_path):
    """The written JSON file must contain the auditors snapshot."""
    from app.services.audit_service import write_post_run_audit

    project, project_root, session_root = _setup_project(tmp_path)

    mock_auditors = {
        "session": {"status": "ready", "blockers": []},
        "planner": {"status": "blocked", "blockers": ["2 duplicate task file(s) detected."]},
        "ontology": {"status": "ready", "blockers": []},
        "integrity": {"status": "ready", "blockers": []},
        "closeout": {"status": "ready", "blockers": []},
    }

    with (
        patch("app.services.audit_service.planner_service.ensure_main_board", new_callable=AsyncMock, return_value={"_id": "main"}),
        patch("app.services.audit_service.planner_service.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.auditor_service.build_auditor_statuses", new_callable=AsyncMock, return_value=mock_auditors),
    ):
        result = await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-003",
            session={"role": "planner"},
            changed_files=[],
        )

    json_path = Path(result["jsonPath"])
    assert json_path.exists()
    on_disk = json.loads(json_path.read_text(encoding="utf-8"))
    assert on_disk["auditors"]["planner"]["status"] == "blocked"
    assert "2 duplicate" in on_disk["auditors"]["planner"]["blockers"][0]


@pytest.mark.asyncio
async def test_write_post_run_audit_skips_identical_payload(tmp_path):
    """Identical audit payloads must short-circuit before touching disk or git.

    This is the regression guard for the autopilot/reconciliation loop that
    produced 8+ "audit: durable post-run certificates" commits for the same
    unchanged session payload.
    """
    from app.services.audit_service import write_post_run_audit

    project, project_root, session_root = _setup_project(tmp_path)
    subprocess.run(["git", "-C", str(project_root), "init", "-b", "main"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.name", "RAIL Test"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.email", "rail-test@example.com"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "bootstrap"], check=True, capture_output=True, text=True)

    with (
        patch("app.services.audit_service.planner_service.ensure_main_board", new_callable=AsyncMock, return_value={"_id": "main"}),
        patch("app.services.audit_service.planner_service.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.auditor_service.build_auditor_statuses", new_callable=AsyncMock, return_value={}),
    ):
        first = await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-idem",
            session={"role": "research"},
            changed_files=["topics/source_notes.md"],
        )
        head_after_first = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        first_mtime = Path(first["jsonPath"]).stat().st_mtime_ns

        # Rewrite with no state change. The payload is identical (modulo
        # generatedAt, which is excluded from the hash) so nothing should
        # touch disk or git.
        second = await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-idem",
            session={"role": "research"},
            changed_files=["topics/source_notes.md"],
        )

    head_after_second = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    second_mtime = Path(second["jsonPath"]).stat().st_mtime_ns
    status = subprocess.run(
        ["git", "-C", str(project_root), "status", "--short", "--", "research_plan/audits/sess-idem.json"],
        check=True, capture_output=True, text=True,
    ).stdout

    assert second.get("skipped") is True
    assert head_after_first == head_after_second
    assert first_mtime == second_mtime, "audit JSON was rewritten despite identical payload"
    assert status == "", "working tree should be clean — no audit churn on identical payload"
    assert first["payload"]["payloadHash"] == second["payload"]["payloadHash"]


@pytest.mark.asyncio
async def test_write_post_run_audit_does_not_recommit_existing_session_audit(tmp_path):
    from app.services.audit_service import write_post_run_audit

    project, project_root, session_root = _setup_project(tmp_path)

    subprocess.run(["git", "-C", str(project_root), "init", "-b", "main"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.name", "RAIL Test"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "config", "user.email", "rail-test@example.com"], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "add", "."], check=True, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(project_root), "commit", "-m", "bootstrap"], check=True, capture_output=True, text=True)

    with (
        patch("app.services.audit_service.planner_service.ensure_main_board", new_callable=AsyncMock, return_value={"_id": "main"}),
        patch("app.services.audit_service.planner_service.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.auditor_service.build_auditor_statuses", new_callable=AsyncMock, return_value={}),
    ):
        await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-001",
            session={"role": "research"},
            changed_files=["topics/source_notes.md"],
        )
        first_head = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        # Force a content refresh on the same audit file; it should update the
        # worktree copy but not mint another dedicated audit-history commit.
        state = {"session_id": "sess-001", "status": "completed", "review_status": "review", "publish_status": "failed"}
        (session_root / "state.json").write_text(json.dumps(state), encoding="utf-8")
        await write_post_run_audit(
            project=project,
            project_root=project_root,
            session_root=session_root,
            session_id="sess-001",
            session={"role": "research"},
            changed_files=["topics/source_notes.md"],
        )

    second_head = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    audit_commit_count = subprocess.run(
        ["git", "-C", str(project_root), "rev-list", "--count", "--grep=^audit: durable post-run certificates", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(project_root), "status", "--short", "--", "research_plan/audits/sess-001.json", "research_plan/audits/sess-001.md"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert first_head == second_head
    assert audit_commit_count == "1"
    assert "research_plan/audits/sess-001.json" in status


def test_audit_gate_status_reports_stale_session_details(tmp_path):
    from app.services.audit_service import audit_gate_status
    from app.services import session_files

    project, project_root, session_root = _setup_project(tmp_path)
    session_files.write_state(
        session_root,
        {
            "session_id": "sess-001",
            "status": "completed",
            "review_status": "review",
            "updated_at": "2026-05-21T00:10:00Z",
        },
    )

    gate = audit_gate_status(project_root)

    assert gate["blocked"] is True
    assert gate["staleSessionIds"] == ["sess-001"]
    assert gate["staleSessionDetails"][0]["sessionId"] == "sess-001"
    assert gate["staleSessionDetails"][0]["reason"] == "no_latest_audit"
