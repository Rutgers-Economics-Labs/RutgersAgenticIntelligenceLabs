from __future__ import annotations

from pathlib import Path

import asyncio
import pytest

from app.services.safe_publish_service import (
    collect_publishable_files,
    is_repo_publish_path_allowed,
    normalize_repo_publish_path,
    publish_repo_files,
    record_publish_failure,
    record_publish_success,
    rollback_project_update,
)
from rail.bootstrap import bootstrap_future_project


def test_normalize_repo_publish_path_preserves_dot_directories() -> None:
    assert normalize_repo_publish_path(".ontology/sources/example.yaml") == ".ontology/sources/example.yaml"
    assert normalize_repo_publish_path("./.ontology/sources/example.yaml") == ".ontology/sources/example.yaml"
    assert normalize_repo_publish_path("topics/source_notes.md") == "topics/source_notes.md"


def test_is_repo_publish_path_allowed_allows_dot_ontology_paths() -> None:
    assert is_repo_publish_path_allowed(".ontology/sources/example.yaml")
    assert is_repo_publish_path_allowed(".ontology/pipelines/example.yaml")
    assert not is_repo_publish_path_allowed("../.ontology/sources/example.yaml")


def test_collect_publishable_files_includes_dot_ontology_files(tmp_path: Path) -> None:
    repo_root = tmp_path
    source_path = repo_root / ".ontology" / "sources" / "example.yaml"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("name: example\n", encoding="utf-8")

    files, skipped = collect_publishable_files(
        repo_root,
        [".ontology/sources/example.yaml"],
    )

    assert skipped == []
    assert files == [{"path": ".ontology/sources/example.yaml", "content": "name: example\n"}]


def test_collect_publishable_files_preserves_binary_content(tmp_path: Path) -> None:
    repo_root = tmp_path
    duckdb_path = repo_root / ".ontology" / "onto.duckdb"
    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    duckdb_path.write_bytes(b"\x80DUCK")

    files, skipped = collect_publishable_files(
        repo_root,
        [".ontology/onto.duckdb"],
    )

    assert skipped == []
    assert files == [{"path": ".ontology/onto.duckdb", "content": b"\x80DUCK"}]


def test_record_publish_metadata_is_noop_with_current_project_schema(monkeypatch) -> None:
    called = False

    async def _unexpected_mutation(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.safe_publish_service.convex.mutation", _unexpected_mutation)

    asyncio.run(record_publish_success("project-1", {"commit_sha": "deadbeef"}))
    asyncio.run(record_publish_failure("project-1", "failed"))

    assert called is False


def test_rollback_project_update_skips_unsupported_publish_metadata(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _record_mutation(name: str, payload: dict):
        calls.append((name, payload))

    monkeypatch.setattr("app.services.safe_publish_service.convex.mutation", _record_mutation)

    previous = {
        "name": "Project",
        "description": "desc",
        "gitRepoUrl": "https://github.com/example/repo",
        "localRepoPath": "/tmp/project",
        "manifestPath": "rail.yaml",
        "ontologyConfigSlug": "ontology",
        "apiConfigSlugs": ["api"],
        "pipelineConfigSlug": "pipeline",
        "status": "draft",
        "creationStatus": "completed",
        "briefHash": "hash",
        "researchGraphSummary": {"x": 1},
        "sourceReadinessCounts": {"ready": 1},
        "lastJobId": "job-1",
        "activeOntologyDbPath": "a.db",
        "activeOntologyOwlPath": "a.owl",
        "activeOntologyDuckdbPath": "a.duckdb",
        "activeOntologyEmbeddingsPath": "a.npz",
        "github": "org/repo",
        "defaultBranch": "main",
        "githubSyncMode": "auto_safe",
        "lastPublishedCommitSha": "deadbeef",
        "lastPublishedAt": 123,
        "lastPublishError": "boom",
        "ontologyTemplates": ["t1"],
        "agentModel": "gpt",
        "agentAllowedActions": ["read"],
        "lastHydratedAt": 456,
    }

    asyncio.run(rollback_project_update("project-1", previous))

    assert calls[0][0] == "projects:updateById"
    payload = calls[0][1]
    assert "lastPublishedCommitSha" not in payload
    assert "lastPublishedAt" not in payload
    assert "lastPublishError" not in payload
    assert "githubSyncMode" not in payload
    assert "creationStatus" not in payload


def test_publish_repo_files_blocks_artifact_publish_when_ontology_auditor_is_blocked(tmp_path: Path, monkeypatch) -> None:
    root = bootstrap_future_project(tmp_path, name="Publish Gate Project", slug="publish-gate-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n", encoding="utf-8")

    project = {
        "_id": "project-1",
        "slug": "publish-gate-project",
        "localRepoPath": str(root),
        "github": "org/repo",
        "defaultBranch": "main",
    }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "ready", "blockers": []},
        }

    async def _unexpected_commit(*args, **kwargs):
        raise AssertionError("artifact publish should not reach GitHub commit when ontology auditor is blocked")

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr("app.services.safe_publish_service.github_service.commit_files", _unexpected_commit)

    with pytest.raises(RuntimeError, match="Artifact publish blocked by auditor state: ontology:"):
        asyncio.run(
            publish_repo_files(
                project,
                repo_root=root,
                changed_paths=["artifacts/report.md"],
                commit_message="publish report",
            )
        )


def test_publish_repo_files_allows_non_artifact_publish_when_ontology_auditor_is_blocked(tmp_path: Path, monkeypatch) -> None:
    root = bootstrap_future_project(tmp_path, name="Publish Gate Project", slug="publish-gate-project")
    task_path = root / "research_plan" / "tasks" / "repair.md"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text("# Repair\n", encoding="utf-8")

    project = {
        "_id": "project-1",
        "slug": "publish-gate-project",
        "localRepoPath": str(root),
        "github": "org/repo",
        "defaultBranch": "main",
    }

    async def _build_auditor_statuses(project_arg, *, tasks=None, active_sessions=None):
        return {
            "ontology": {"status": "blocked", "blockers": ["Ontology hydration state is `not_hydrated`."]},
            "integrity": {"status": "ready", "blockers": []},
        }

    calls: list[dict[str, object]] = []

    async def _commit_files(repo: str, branch: str, files: list[dict[str, object]], message: str):
        calls.append({"repo": repo, "branch": branch, "files": files, "message": message})
        return {"commit_sha": "deadbeef", "branch": branch, "changed": True, "files": files}

    monkeypatch.setattr("app.services.auditor_service.build_auditor_statuses", _build_auditor_statuses)
    monkeypatch.setattr("app.services.safe_publish_service.github_service.commit_files", _commit_files)

    result = asyncio.run(
        publish_repo_files(
            project,
            repo_root=root,
            changed_paths=["research_plan/tasks/repair.md"],
            commit_message="publish repair task",
        )
    )

    assert result["published"] is True
    assert result["commit_sha"] == "deadbeef"
    assert calls[0]["files"] == [{"path": "research_plan/tasks/repair.md", "content": "# Repair\n"}]
