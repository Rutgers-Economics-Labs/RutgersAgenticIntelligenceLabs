from __future__ import annotations

import httpx
import pytest

from app.services.github_service import GitHubService


@pytest.mark.asyncio
async def test_commit_files_retries_once_on_ref_race(monkeypatch: pytest.MonkeyPatch) -> None:
    service = GitHubService()

    async def _token(repo: str) -> str:
        return "token"

    heads = iter(["head-a", "head-b"])

    async def _head(repo: str, branch: str) -> str:
        return next(heads)

    async def _metadata(repo: str, path: str, ref: str = "main"):
        return None

    async def _commit(repo: str, commit_sha: str) -> dict:
        return {"tree": {"sha": f"tree-for-{commit_sha}"}}

    async def _blob(repo: str, content: str, *, token: str | None = None) -> str:
        return "blob-sha"

    async def _tree(repo: str, base_tree_sha: str, tree: list[dict], *, token: str | None = None) -> str:
        return f"tree-{base_tree_sha}"

    created_commits: list[tuple[str, str]] = []

    async def _create_commit(repo: str, message: str, tree_sha: str, parent_sha: str, *, token: str | None = None) -> str:
        created_commits.append((tree_sha, parent_sha))
        return f"commit-for-{parent_sha}"

    update_calls = {"count": 0}

    async def _update_ref(repo: str, branch: str, commit_sha: str, *, token: str | None = None) -> None:
        update_calls["count"] += 1
        if update_calls["count"] == 1:
            request = httpx.Request("PATCH", f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}")
            response = httpx.Response(422, request=request)
            raise httpx.HTTPStatusError("ref race", request=request, response=response)

    monkeypatch.setattr(service, "get_installation_token", _token)
    monkeypatch.setattr(service, "get_branch_head", _head)
    monkeypatch.setattr(service, "get_file_metadata", _metadata)
    monkeypatch.setattr(service, "get_commit", _commit)
    monkeypatch.setattr(service, "create_blob", _blob)
    monkeypatch.setattr(service, "create_tree", _tree)
    monkeypatch.setattr(service, "create_commit", _create_commit)
    monkeypatch.setattr(service, "update_ref", _update_ref)

    result = await service.commit_files(
        "Rutgers-Economics-Labs/example",
        "main",
        [{"path": ".ontology/sources/example.yaml", "content": "name: example\n"}],
        "test commit",
    )

    assert result["changed"] is True
    assert result["commit_sha"] == "commit-for-head-b"
    assert update_calls["count"] == 2
    assert created_commits == [
        ("tree-tree-for-head-a", "head-a"),
        ("tree-tree-for-head-b", "head-b"),
    ]


@pytest.mark.asyncio
async def test_commit_files_treats_post_race_matching_remote_content_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GitHubService()

    async def _token(repo: str) -> str:
        return "token"

    heads = iter(["head-a", "head-b", "head-c"])

    async def _head(repo: str, branch: str) -> str:
        return next(heads)

    incoming = b"name: example\n"
    metadata_calls: list[str] = []

    async def _metadata(repo: str, path: str, ref: str = "main"):
        metadata_calls.append(ref)
        if ref == "main":
            return None
        return {"content_bytes": incoming}

    async def _commit(repo: str, commit_sha: str) -> dict:
        return {"tree": {"sha": f"tree-for-{commit_sha}"}}

    async def _blob(repo: str, content: str, *, token: str | None = None) -> str:
        return "blob-sha"

    async def _tree(repo: str, base_tree_sha: str, tree: list[dict], *, token: str | None = None) -> str:
        return f"tree-{base_tree_sha}"

    async def _create_commit(repo: str, message: str, tree_sha: str, parent_sha: str, *, token: str | None = None) -> str:
        return f"commit-for-{parent_sha}"

    async def _update_ref(repo: str, branch: str, commit_sha: str, *, token: str | None = None) -> None:
        request = httpx.Request("PATCH", f"https://api.github.com/repos/{repo}/git/refs/heads/{branch}")
        response = httpx.Response(422, request=request)
        raise httpx.HTTPStatusError("ref race", request=request, response=response)

    monkeypatch.setattr(service, "get_installation_token", _token)
    monkeypatch.setattr(service, "get_branch_head", _head)
    monkeypatch.setattr(service, "get_file_metadata", _metadata)
    monkeypatch.setattr(service, "get_commit", _commit)
    monkeypatch.setattr(service, "create_blob", _blob)
    monkeypatch.setattr(service, "create_tree", _tree)
    monkeypatch.setattr(service, "create_commit", _create_commit)
    monkeypatch.setattr(service, "update_ref", _update_ref)

    result = await service.commit_files(
        "Rutgers-Economics-Labs/example",
        "main",
        [{"path": ".ontology/sources/example.yaml", "content": incoming.decode("utf-8")}],
        "test commit",
    )

    assert result["changed"] is False
    assert result["commit_sha"] == "head-c"
    assert metadata_calls == ["main", "head-c"]
