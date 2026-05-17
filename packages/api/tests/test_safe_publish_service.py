from __future__ import annotations

from pathlib import Path

import asyncio

from app.services.safe_publish_service import (
    collect_publishable_files,
    is_repo_publish_path_allowed,
    normalize_repo_publish_path,
    record_publish_failure,
    record_publish_success,
    rollback_project_update,
)


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
