"""Tests for Milestone 9: Controlled Parallelism — task ownership declarations."""

from __future__ import annotations

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
