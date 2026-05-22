"""Tests for Milestone 9: Controlled Parallelism — task ownership declarations."""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# declare_task_ownership
# ---------------------------------------------------------------------------

def test_declare_task_ownership_creates_lock_file(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership, read_task_ownership

    claim = declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    assert claim["taskId"] == "task-001"
    assert claim["sessionId"] == "sess-aaa"
    assert "claimedAt" in claim

    on_disk = read_task_ownership("task-001", project_root=tmp_path)
    assert on_disk is not None
    assert on_disk["sessionId"] == "sess-aaa"


def test_declare_task_ownership_same_session_is_idempotent(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)
    claim2 = declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    assert claim2["sessionId"] == "sess-aaa"


def test_declare_task_ownership_raises_when_owned_by_other_session(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    with pytest.raises(RuntimeError, match="sess-aaa"):
        declare_task_ownership("task-001", "sess-bbb", project_root=tmp_path)


# ---------------------------------------------------------------------------
# read_task_ownership
# ---------------------------------------------------------------------------

def test_read_task_ownership_returns_none_when_not_claimed(tmp_path):
    from app.services.task_ownership_service import read_task_ownership

    result = read_task_ownership("task-999", project_root=tmp_path)

    assert result is None


# ---------------------------------------------------------------------------
# release_task_ownership
# ---------------------------------------------------------------------------

def test_release_task_ownership_removes_lock_file(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership, release_task_ownership, read_task_ownership

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)
    result = release_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    assert result["released"] is True
    assert read_task_ownership("task-001", project_root=tmp_path) is None


def test_release_task_ownership_not_claimed_returns_false(tmp_path):
    from app.services.task_ownership_service import release_task_ownership

    result = release_task_ownership("task-999", "sess-aaa", project_root=tmp_path)

    assert result["released"] is False
    assert result["reason"] == "task_not_claimed"


def test_release_task_ownership_wrong_session_raises(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership, release_task_ownership

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    with pytest.raises(RuntimeError, match="sess-bbb"):
        release_task_ownership("task-001", "sess-bbb", project_root=tmp_path)


# ---------------------------------------------------------------------------
# list_owned_tasks
# ---------------------------------------------------------------------------

def test_list_owned_tasks_returns_all_claims(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership, list_owned_tasks

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)
    declare_task_ownership("task-002", "sess-bbb", project_root=tmp_path)

    claims = list_owned_tasks(tmp_path)

    assert len(claims) == 2
    task_ids = {c["taskId"] for c in claims}
    assert task_ids == {"task-001", "task-002"}


def test_list_owned_tasks_empty_when_no_locks(tmp_path):
    from app.services.task_ownership_service import list_owned_tasks

    result = list_owned_tasks(tmp_path)

    assert result == []


def test_list_owned_tasks_reflects_releases(tmp_path):
    from app.services.task_ownership_service import declare_task_ownership, release_task_ownership, list_owned_tasks

    declare_task_ownership("task-001", "sess-aaa", project_root=tmp_path)
    declare_task_ownership("task-002", "sess-bbb", project_root=tmp_path)
    release_task_ownership("task-001", "sess-aaa", project_root=tmp_path)

    claims = list_owned_tasks(tmp_path)

    assert len(claims) == 1
    assert claims[0]["taskId"] == "task-002"


# ---------------------------------------------------------------------------
# Audited Merge (Milestone 9)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audited_merge_success(tmp_path, monkeypatch):
    """Test that a completed, verified session automatically merges its workspace branch."""
    from app.runners import session_lifecycle
    from app.runners.session_lifecycle import _finalize_workspace_review
    from app.services import session_files

    # 1. Setup mock session state
    session_root = tmp_path / ".rail" / "sessions" / "agent" / "sess-123"
    session_root.mkdir(parents=True)
    workspace_root = tmp_path / ".rail" / "workspaces" / "sess-123"
    workspace_root.mkdir(parents=True)

    session_files.write_state(session_root, {
        "status": "completed",
        "verification_status": "passed",
        "publish_status": "published",
        "publish_branch": "agent-sess-123",
        "workspace_path": str(workspace_root),
        "workspace_branch": "agent-sess-123",
    })

    (tmp_path / "rail.yaml").write_text("dummy", encoding="utf-8")

    # 2. Mock dependencies
    project = {
        "github": "test/repo",
        "defaultBranch": "main"
    }

    class MockRailManifest:
        pass

    async def mock_write_post_run_audit(*args, **kwargs):
        pass
    monkeypatch.setattr("app.runners.session_lifecycle.write_post_run_audit", mock_write_post_run_audit)

    async def mock_publish(*args, **kwargs):
        pass
    monkeypatch.setattr(session_lifecycle, "_publish_completed_session_outputs", mock_publish)

    class MockGithubService:
        def __init__(self):
            self.merged = False
            self.base = None
            self.head = None

        async def merge_branch(self, repo, base, head, commit_message=None):
            self.merged = True
            self.base = base
            self.head = head
            return {"sha": "merge-123"}

    mock_github = MockGithubService()
    monkeypatch.setattr("app.services.github_service.github_service", mock_github)

    # Mocking list changed files to not crash
    async def mock_list_changed_files(*args, **kwargs):
        return []
    monkeypatch.setattr(session_lifecycle, "_list_changed_files", mock_list_changed_files)

    # Mocking summary generator
    async def mock_normalize_summary(*args, **kwargs):
        return {"blockers": [], "recommended_next_tasks": []}
    monkeypatch.setattr(session_lifecycle, "_normalize_completion_summary", mock_normalize_summary)

    # 3. Execute
    await _finalize_workspace_review(
        convex_session_id="sess-123",
        session={"role": "agent"},
        project=project,
        project_root=tmp_path,
        session_root=session_root,
        base_branch="main",
    )

    # 4. Verify merge was called
    assert mock_github.merged is True
    assert mock_github.base == "main"
    assert mock_github.head == "agent-sess-123"

@pytest.mark.asyncio
async def test_audited_merge_failure_marks_needs_changes(tmp_path, monkeypatch):
    """Test that a merge conflict marks the session as needs_changes and logs the error."""
    from app.runners import session_lifecycle
    from app.runners.session_lifecycle import _finalize_workspace_review
    from app.services import session_files

    # 1. Setup mock session state
    session_root = tmp_path / ".rail" / "sessions" / "agent" / "sess-123"
    session_root.mkdir(parents=True)
    workspace_root = tmp_path / ".rail" / "workspaces" / "sess-123"
    workspace_root.mkdir(parents=True)
    
    session_files.write_state(session_root, {
        "status": "completed",
        "verification_status": "passed",
        "publish_status": "published",
        "publish_branch": "agent-sess-123",
        "workspace_path": str(workspace_root),
        "workspace_branch": "agent-sess-123",
    })
    (session_root / "events.json").write_text("[]", encoding="utf-8")

    (tmp_path / "rail.yaml").write_text("dummy", encoding="utf-8")

    # 2. Mock dependencies
    project = {
        "github": "test/repo",
        "defaultBranch": "main"
    }

    class MockRailManifest:
        pass
        
    async def mock_write_post_run_audit(*args, **kwargs):
        pass
    monkeypatch.setattr("app.runners.session_lifecycle.write_post_run_audit", mock_write_post_run_audit)

    async def mock_publish(*args, **kwargs):
        pass
    monkeypatch.setattr("app.runners.session_lifecycle._publish_completed_session_outputs", mock_publish)

    class MockGithubService:
        async def merge_branch(self, repo, base, head, commit_message=None):
            raise Exception("Merge conflict detected")
            
    mock_github = MockGithubService()
    monkeypatch.setattr("app.services.github_service.github_service", mock_github)
    
    # Mocking list changed files
    async def mock_list_changed_files(*args, **kwargs):
        return []
    monkeypatch.setattr(session_lifecycle, "_list_changed_files", mock_list_changed_files)
    
    # Mocking summary generator
    async def mock_normalize_summary(*args, **kwargs):
        return {"blockers": [], "recommended_next_tasks": []}
    monkeypatch.setattr(session_lifecycle, "_normalize_completion_summary", mock_normalize_summary)

    # 3. Execute
    await _finalize_workspace_review(
        convex_session_id="sess-123",
        session={"role": "agent"},
        project=project,
        project_root=tmp_path,
        session_root=session_root,
        base_branch="main",
    )

    # 4. Verify state updated to reflect failure
    state = session_files.read_state(session_root)
    assert state["publish_status"] == "failed"
    assert "Merge conflict detected" in state["publish_error"]


@pytest.mark.asyncio
async def test_audited_merge_skipped_when_publish_already_targeted_base_branch(tmp_path, monkeypatch):
    """If publish already committed directly to the base branch, merge should be skipped."""
    from app.runners import session_lifecycle
    from app.runners.session_lifecycle import _finalize_workspace_review
    from app.services import session_files

    session_root = tmp_path / ".rail" / "sessions" / "agent" / "sess-123"
    session_root.mkdir(parents=True)
    workspace_root = tmp_path / ".rail" / "workspaces" / "sess-123"
    workspace_root.mkdir(parents=True)

    session_files.write_state(session_root, {
        "status": "completed",
        "verification_status": "passed",
        "publish_status": "published",
        "publish_branch": "main",
        "workspace_path": str(workspace_root),
        "workspace_branch": "agent-sess-123",
    })

    (tmp_path / "rail.yaml").write_text("dummy", encoding="utf-8")

    project = {
        "github": "test/repo",
        "defaultBranch": "main",
    }

    async def mock_write_post_run_audit(*args, **kwargs):
        pass
    monkeypatch.setattr("app.runners.session_lifecycle.write_post_run_audit", mock_write_post_run_audit)

    async def mock_publish(*args, **kwargs):
        pass
    monkeypatch.setattr(session_lifecycle, "_publish_completed_session_outputs", mock_publish)

    class MockGithubService:
        def __init__(self):
            self.called = False

        async def merge_branch(self, repo, base, head, commit_message=None):
            self.called = True
            return {"sha": "merge-123"}

    mock_github = MockGithubService()
    monkeypatch.setattr("app.services.github_service.github_service", mock_github)

    async def mock_list_changed_files(*args, **kwargs):
        return []
    monkeypatch.setattr(session_lifecycle, "_list_changed_files", mock_list_changed_files)

    async def mock_normalize_summary(*args, **kwargs):
        return {"blockers": [], "recommended_next_tasks": []}
    monkeypatch.setattr(session_lifecycle, "_normalize_completion_summary", mock_normalize_summary)

    await _finalize_workspace_review(
        convex_session_id="sess-123",
        session={"role": "agent"},
        project=project,
        project_root=tmp_path,
        session_root=session_root,
        base_branch="main",
    )

    state = session_files.read_state(session_root)
    assert mock_github.called is False
    assert state["publish_status"] == "published"


@pytest.mark.asyncio
async def test_audited_merge_404_after_direct_base_publish_does_not_flip_publish_failed(tmp_path, monkeypatch):
    """If a stale finalize path still attempts merge after direct base publish, keep publish green."""
    from app.runners import session_lifecycle
    from app.runners.session_lifecycle import _finalize_workspace_review
    from app.services import session_files

    session_root = tmp_path / ".rail" / "sessions" / "agent" / "sess-123"
    session_root.mkdir(parents=True)
    workspace_root = tmp_path / ".rail" / "workspaces" / "sess-123"
    workspace_root.mkdir(parents=True)

    session_files.write_state(session_root, {
        "status": "completed",
        "verification_status": "passed",
        "publish_status": "published",
        "publish_branch": "agent-sess-123",
        "workspace_path": str(workspace_root),
        "workspace_branch": "agent-sess-123",
    })

    (tmp_path / "rail.yaml").write_text("dummy", encoding="utf-8")

    project = {
        "github": "test/repo",
        "defaultBranch": "main",
    }

    async def mock_write_post_run_audit(*args, **kwargs):
        pass
    monkeypatch.setattr("app.runners.session_lifecycle.write_post_run_audit", mock_write_post_run_audit)

    async def mock_publish(*args, **kwargs):
        session_files.update_state(
            session_root,
            publish_status="published",
            publish_branch="main",
            publish_error="",
            publish_commit_sha="abc123",
        )
        return {
            "published": True,
            "strategy": "github_app_commit",
            "commit_sha": "abc123",
            "branch": "main",
            "changed": True,
            "files": [{"path": "research_plan/state/artifact_lineage.json", "changed": True}],
            "skipped_files": [],
        }
    monkeypatch.setattr(session_lifecycle, "_publish_completed_session_outputs", mock_publish)

    class MockGithubService:
        async def merge_branch(self, repo, base, head, commit_message=None):
            raise Exception("Client error '404 Not Found' for url 'https://api.github.com/repos/test/repo/merges'")

    monkeypatch.setattr("app.services.github_service.github_service", MockGithubService())

    async def mock_list_changed_files(*args, **kwargs):
        return ["research_plan/state/artifact_lineage.json"]
    monkeypatch.setattr(session_lifecycle, "_list_changed_files", mock_list_changed_files)

    async def mock_normalize_summary(*args, **kwargs):
        return {"blockers": [], "recommended_next_tasks": []}
    monkeypatch.setattr(session_lifecycle, "_normalize_completion_summary", mock_normalize_summary)

    await _finalize_workspace_review(
        convex_session_id="sess-123",
        session={"role": "agent"},
        project=project,
        project_root=tmp_path,
        session_root=session_root,
        base_branch="main",
    )

    state = session_files.read_state(session_root)
    assert state["publish_status"] == "published"
    assert state.get("publish_error", "") == ""
