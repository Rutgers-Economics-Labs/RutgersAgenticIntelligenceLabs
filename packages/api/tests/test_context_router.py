from __future__ import annotations

import json

import httpx
import pytest

from app.routers import context as context_router
from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo

pytestmark = pytest.mark.asyncio


async def test_add_text_syncs_source_and_chunks_into_repo(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Context Project", slug="context-project")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Context Project",
                        "slug": "context-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            assert payload["args"]["projectSlug"] == "context-project"
            assert "projectId" not in payload["args"]
            return httpx.Response(200, json={"value": "doc-123"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Grid Briefing",
            "content": "This note explains congestion, interconnection queues, and transmission reliability in the PJM region.",
            "project_id": "project-id",
        },
    )

    assert resp.status_code == 200
    repo = ResearchIntegrityRepo(root)
    sources = repo.load_sources()
    chunks = repo.load_evidence_chunks()
    source = next(source for source in sources if source.source_key == "context-doc-123")
    source_chunks = [chunk for chunk in chunks if chunk.source_key == "context-doc-123"]

    assert source.source_type == "text"
    assert source.title == "Grid Briefing"
    assert source.url_or_path == "Grid Briefing"
    assert source.origin == "context:text"
    assert source.access_method == "manual"
    assert source.freshness_status == "fresh"
    assert source.quality_status == "candidate"
    assert source.provenance["context_doc_id"] == "doc-123"
    assert source.provenance["ingest_path"] == "context"
    assert "interconnection queues" in source.provenance["text"]
    assert source_chunks
    assert all(chunk.metadata["source_title"] == "Grid Briefing" for chunk in source_chunks)
    assert all(chunk.metadata["source_type"] == "text" for chunk in source_chunks)
    assert all(chunk.metadata["origin"] == "context:text" for chunk in source_chunks)


async def test_add_url_syncs_source_and_chunks_into_repo(client, convex_mock, tmp_path, monkeypatch):
    root = bootstrap_future_project(tmp_path, name="Context Project", slug="context-project")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Context Project",
                        "slug": "context-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            assert payload["args"]["projectSlug"] == "context-project"
            assert "projectId" not in payload["args"]
            return httpx.Response(200, json={"value": "doc-456"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)
    monkeypatch.setattr(
        context_router,
        "_scrape_url",
        lambda url: "Queue backlogs worsened after 2021 because congestion and transmission delays increased.",
    )

    resp = await client.post(
        "/api/v1/context/url",
        json={
            "url": "https://example.com/queue-brief",
            "name": "Queue Brief",
            "project_id": "project-id",
        },
    )

    assert resp.status_code == 200
    repo = ResearchIntegrityRepo(root)
    sources = repo.load_sources()
    chunks = repo.load_evidence_chunks()
    source = next(source for source in sources if source.source_key == "context-doc-456")
    source_chunks = [chunk for chunk in chunks if chunk.source_key == "context-doc-456"]

    assert source.source_type == "url"
    assert source.title == "Queue Brief"
    assert source.url_or_path == "https://example.com/queue-brief"
    assert source.origin == "example.com"
    assert source.access_method == "web"
    assert source.freshness_status == "fresh"
    assert source.quality_status == "candidate"
    assert source.provenance["context_doc_id"] == "doc-456"
    assert source.provenance["ingest_path"] == "context"
    assert "transmission delays increased" in source.provenance["text"]
    assert source_chunks
    assert all(chunk.metadata["source_title"] == "Queue Brief" for chunk in source_chunks)
    assert all(chunk.metadata["source_type"] == "url" for chunk in source_chunks)
    assert all(chunk.metadata["origin"] == "example.com" for chunk in source_chunks)


async def test_upload_text_file_syncs_source_and_chunks_into_repo(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Context Project", slug="context-project")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Context Project",
                        "slug": "context-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            assert payload["args"]["projectSlug"] == "context-project"
            assert "projectId" not in payload["args"]
            return httpx.Response(200, json={"value": "doc-789"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    resp = await client.post(
        "/api/v1/context/upload",
        files={"file": ("queue-notes.txt", b"Congestion worsened and queue times increased after 2021.", "text/plain")},
        data={"project_id": "project-id", "name": "Queue Notes"},
    )

    assert resp.status_code == 200
    repo = ResearchIntegrityRepo(root)
    sources = repo.load_sources()
    chunks = repo.load_evidence_chunks()
    source = next(source for source in sources if source.source_key == "context-doc-789")
    source_chunks = [chunk for chunk in chunks if chunk.source_key == "context-doc-789"]

    assert source.source_type == "text"
    assert source.title == "Queue Notes"
    assert source.url_or_path == "queue-notes.txt"
    assert source.origin == "queue-notes.txt"
    assert source.access_method == "upload"
    assert source.freshness_status == "fresh"
    assert source.quality_status == "candidate"
    assert source.provenance["context_doc_id"] == "doc-789"
    assert source.provenance["ingest_path"] == "context"
    assert "queue times increased" in source.provenance["text"]
    assert source_chunks
    assert all(chunk.metadata["source_title"] == "Queue Notes" for chunk in source_chunks)
    assert all(chunk.metadata["source_type"] == "text" for chunk in source_chunks)
    assert all(chunk.metadata["origin"] == "queue-notes.txt" for chunk in source_chunks)


async def test_add_text_syncs_source_for_local_repo_only_project_id(
    client, convex_mock, tmp_path, monkeypatch
):
    root = bootstrap_future_project(tmp_path, name="Context Project", slug="context-project")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in {"projects:getById", "projects:get"}:
            return httpx.Response(200, json={"value": None})
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            assert payload["args"]["projectSlug"] == "context-project"
            assert "projectId" not in payload["args"]
            return httpx.Response(200, json={"value": "doc-local"})
        return httpx.Response(200, json={"value": None})

    async def _get_project_by_slug(slug: str):
        if slug != "context-project":
            raise ValueError(slug)
        return {
            "_id": "local:context-project",
            "name": "Context Project",
            "slug": "context-project",
            "status": "ready",
            "localRepoPath": str(root),
        }

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)
    monkeypatch.setattr(context_router.planner_service, "get_project_by_slug", _get_project_by_slug)

    resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Repo Only Note",
            "content": "Repo-only projects should still sync context notes into integrity.",
            "project_id": "local:context-project",
        },
    )

    assert resp.status_code == 200
    repo = ResearchIntegrityRepo(root)
    sources = repo.load_sources()
    source = next(source for source in sources if source.source_key == "context-doc-local")

    assert source.title == "Repo Only Note"
    assert source.source_type == "text"
    assert source.provenance["context_doc_id"] == "doc-local"
