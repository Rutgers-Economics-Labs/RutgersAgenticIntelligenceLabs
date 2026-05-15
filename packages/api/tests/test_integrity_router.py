from __future__ import annotations

import json

import httpx
import pytest

from rail.bootstrap import bootstrap_future_project
from rail.integrity import ResearchIntegrityRepo

pytestmark = pytest.mark.asyncio


async def test_patch_assumption_returns_rerun_plan(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "study-period",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Ontology DuckDB",
                "promotion_state": "verified",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": [".ontology/onto.duckdb"],
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/assumptions/study-period",
        json={"value": "2012-2024", "notes": "Updated analysis window"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["assumption"]["value"] == "2012-2024"
    assert payload["rerunPlan"]["affectedPaths"] == [".ontology/onto.duckdb", "artifacts/report.md"]


async def test_apply_rerun_plan_creates_tasks(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_assumptions(
        [
            {
                "assumption_key": "study-period",
                "title": "Study period",
                "value": "2010-2024",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "assumptions": ["research_plan/state/assumptions.json#study-period"],
                "stale_reasons": ["assumption_changed:study-period"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/rerun-plan/apply",
        json={"assumptionKey": "study-period"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["tasks"]) >= 2


async def test_api_acceptance_can_ingest_context_record_claim_and_promote_artifact(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n", encoding="utf-8")
    ontology_path = root / ".ontology" / "onto.duckdb"
    ontology_path.parent.mkdir(parents=True, exist_ok=True)
    ontology_path.write_bytes(b"")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            return httpx.Response(200, json={"value": "doc-123"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    context_resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Regional Queue Brief",
            "content": "Interconnection queue delays increased because congestion worsened after 2021.",
            "project_id": "project-id",
        },
    )
    assert context_resp.status_code == 200

    claim_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/claims",
        json={
            "claimKey": "claim-001",
            "statement": "Queue delays increased after 2021.",
            "artifactPath": "artifacts/report.md",
            "status": "supported",
            "evidencePaths": ["topics/analysis/queue_notes.md"],
            "sourceKeys": ["context-doc-123"],
            "evidenceKind": "direct",
        },
    )
    assert claim_resp.status_code == 200

    artifact_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts",
        json={
            "artifactPath": "artifacts/report.md",
            "artifactType": "report",
            "title": "Report",
            "promotionState": "partially_verified",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "verificationCommands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#context-doc-123"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verificationRuns": ["research_plan/state/verification_runs.json#run-001"],
        },
    )
    assert artifact_resp.status_code == 200

    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Ontology DuckDB",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#context-doc-123"],
            },
            repo.load_artifact_lineage()[0].model_dump(mode="json"),
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "checks": [],
                "artifact_paths": [".ontology/onto.duckdb", "artifacts/report.md"],
                "source_path": "research_plan/state/verification_runs.json",
            }
        ]
    )

    promote_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "verified"},
    )

    assert promote_resp.status_code == 200
    payload = promote_resp.json()
    assert payload["status"] == "promoted"
    assert payload["artifact"]["promotion_state"] == "verified"

    integrity_resp = await client.get("/api/v1/projects/integrity-router-project/integrity")
    assert integrity_resp.status_code == 200
    integrity_payload = integrity_resp.json()
    assert integrity_payload["indexes"]["sources"][0]["source_key"] == "context-doc-123"
    assert integrity_payload["indexes"]["sources"][0]["sourceState"]["isFresh"] is True
    by_path = {item["artifact_path"]: item for item in integrity_payload["indexes"]["artifact_lineage"]}
    assert by_path["artifacts/report.md"]["trustState"]["isTrusted"] is True


async def test_api_acceptance_source_stale_blocks_then_rerun_restores_trust(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("stable report\n", encoding="utf-8")
    ontology_path = root / ".ontology" / "onto.duckdb"
    ontology_path.parent.mkdir(parents=True, exist_ok=True)
    ontology_path.write_bytes(b"")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            return httpx.Response(200, json={"value": "doc-234"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    context_resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Regional Queue Brief",
            "content": "Interconnection queue delays increased because congestion worsened after 2021.",
            "project_id": "project-id",
        },
    )
    assert context_resp.status_code == 200

    claim_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/claims",
        json={
            "claimKey": "claim-001",
            "statement": "Queue delays increased after 2021.",
            "artifactPath": "artifacts/report.md",
            "status": "supported",
            "evidencePaths": ["topics/analysis/queue_notes.md"],
            "sourceKeys": ["context-doc-234"],
            "evidenceKind": "direct",
        },
    )
    assert claim_resp.status_code == 200

    artifact_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts",
        json={
            "artifactPath": "artifacts/report.md",
            "artifactType": "report",
            "title": "Report",
            "promotionState": "verified",
            "inputs": [".ontology/onto.duckdb"],
            "scripts": ["topics/analysis/analyze.py"],
            "verificationCommands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#context-doc-234"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verificationRuns": ["research_plan/state/verification_runs.json#run-001"],
        },
    )
    assert artifact_resp.status_code == 200

    repo = ResearchIntegrityRepo(root)
    report_lineage = repo.load_artifact_lineage()[0].model_dump(mode="json")
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Ontology DuckDB",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#context-doc-234"],
            },
            report_lineage,
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "checks": [],
                "artifact_paths": [".ontology/onto.duckdb", "artifacts/report.md"],
                "source_path": "research_plan/state/verification_runs.json",
            }
        ]
    )

    stale_resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/sources/context-doc-234",
        json={"freshnessStatus": "stale"},
    )
    assert stale_resp.status_code == 200
    assert stale_resp.json()["source"]["freshness_status"] == "stale"

    blocked_promote = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "partially_verified"},
    )
    assert blocked_promote.status_code == 200
    assert blocked_promote.json()["status"] == "blocked"

    refresh_resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/sources/context-doc-234",
        json={"freshnessStatus": "fresh"},
    )
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["source"]["freshness_status"] == "fresh"

    rerun_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/reproducibility-rerun",
        json={
            "outputs": {
                "artifacts/report.md": "stable report\n",
            },
            "runId": "run-002",
            "scope": "health",
        },
    )
    assert rerun_resp.status_code == 200
    assert rerun_resp.json()["status"] == "passed"

    promote_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "verified"},
    )

    assert promote_resp.status_code == 200
    payload = promote_resp.json()
    assert payload["status"] == "promoted"
    assert payload["artifact"]["promotion_state"] == "verified"

    integrity_resp = await client.get("/api/v1/projects/integrity-router-project/integrity")
    assert integrity_resp.status_code == 200
    by_path = {item["artifact_path"]: item for item in integrity_resp.json()["indexes"]["artifact_lineage"]}
    assert by_path["artifacts/report.md"]["trustState"]["isTrusted"] is True


async def test_api_acceptance_conflicting_source_blocks_promotion(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n", encoding="utf-8")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            return httpx.Response(200, json={"value": "doc-345"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    context_resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Regional Queue Brief",
            "content": "Interconnection queue delays increased because congestion worsened after 2021.",
            "project_id": "project-id",
        },
    )
    assert context_resp.status_code == 200

    claim_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/claims",
        json={
            "claimKey": "claim-001",
            "statement": "Queue delays increased after 2021.",
            "artifactPath": "artifacts/report.md",
            "status": "supported",
            "evidencePaths": ["topics/analysis/queue_notes.md"],
            "sourceKeys": ["context-doc-345"],
            "evidenceKind": "direct",
        },
    )
    assert claim_resp.status_code == 200

    artifact_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts",
        json={
            "artifactPath": "artifacts/report.md",
            "artifactType": "report",
            "title": "Report",
            "promotionState": "draft",
            "inputs": ["topics/data.csv"],
            "scripts": ["topics/analyze.py"],
            "verificationCommands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#context-doc-345"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verificationRuns": ["research_plan/state/verification_runs.json#run-001"],
        },
    )
    assert artifact_resp.status_code == 200

    repo = ResearchIntegrityRepo(root)
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "checks": [],
                "artifact_paths": ["artifacts/report.md"],
                "source_path": "research_plan/state/verification_runs.json",
            }
        ]
    )

    blocked_source_resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/sources/context-doc-345",
        json={
            "qualityStatus": "blocked",
            "qualityNotes": "Conflicts with the audited upstream dataset.",
        },
    )

    assert blocked_source_resp.status_code == 200
    assert blocked_source_resp.json()["source"]["quality_status"] == "blocked"

    promote_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "partially_verified"},
    )

    assert promote_resp.status_code == 200
    payload = promote_resp.json()
    assert payload["status"] == "blocked"
    assert "artifacts/report.md" in payload["gate"]["blockingArtifacts"]

    integrity_resp = await client.get("/api/v1/projects/integrity-router-project/integrity")
    assert integrity_resp.status_code == 200
    by_path = {item["artifact_path"]: item for item in integrity_resp.json()["indexes"]["artifact_lineage"]}
    assert by_path["artifacts/report.md"]["promotion_state"] == "blocked"
    assert by_path["artifacts/report.md"]["trustState"]["isBlocked"] is True
    assert by_path["artifacts/report.md"]["trustState"]["isTrusted"] is False


async def test_api_acceptance_missing_lineage_prevents_verification(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n", encoding="utf-8")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "projects:getById":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        if payload.get("path") == "projects:getBySlug":
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    def _mutation(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") == "context:create":
            return httpx.Response(200, json={"value": "doc-456"})
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)
    convex_mock.post("/api/mutation").mock(side_effect=_mutation)

    context_resp = await client.post(
        "/api/v1/context/text",
        json={
            "name": "Regional Queue Brief",
            "content": "Interconnection queue delays increased because congestion worsened after 2021.",
            "project_id": "project-id",
        },
    )
    assert context_resp.status_code == 200

    claim_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/claims",
        json={
            "claimKey": "claim-001",
            "statement": "Queue delays increased after 2021.",
            "artifactPath": "artifacts/report.md",
            "status": "supported",
            "evidencePaths": ["topics/analysis/queue_notes.md"],
            "sourceKeys": ["context-doc-456"],
            "evidenceKind": "direct",
        },
    )
    assert claim_resp.status_code == 200

    artifact_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts",
        json={
            "artifactPath": "artifacts/report.md",
            "artifactType": "report",
            "title": "Report",
            "promotionState": "draft",
            "sources": ["research_plan/state/sources.json#context-doc-456"],
            "claims": ["research_plan/state/claims.json#claim-001"],
        },
    )
    assert artifact_resp.status_code == 200

    promote_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "partially_verified"},
    )

    assert promote_resp.status_code == 200
    payload = promote_resp.json()
    assert payload["status"] == "blocked"
    assert "artifacts/report.md" in payload["gate"]["blockingArtifacts"]

    integrity_resp = await client.get("/api/v1/projects/integrity-router-project/integrity")
    assert integrity_resp.status_code == 200
    by_path = {item["artifact_path"]: item for item in integrity_resp.json()["indexes"]["artifact_lineage"]}
    assert by_path["artifacts/report.md"]["promotion_state"] == "draft"
    assert by_path["artifacts/report.md"]["trustState"]["isTrusted"] is False


async def test_project_integrity_response_includes_normalized_source_and_trust_state(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "grid-source",
                "source_type": "dataset",
                "title": "Grid Source",
                "url_or_path": "https://example.com/grid.csv",
                "origin": "PJM",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#grid-source"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "checks": [],
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get("/api/v1/projects/integrity-router-project/integrity")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["indexes"]["sources"][0]["sourceState"]["isFresh"] is True
    assert payload["indexes"]["artifact_lineage"][0]["verificationStatus"] == "passed"
    assert payload["indexes"]["artifact_lineage"][0]["trustState"]["isTrusted"] is True


async def test_record_integrity_source_and_claim_accept_api_payload_shape(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "lead-source",
            "source_type": "document",
            "title": "Lead Source",
            "url_or_path": "topics/lead.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "A lead source about labor markets."},
        }
    )
    chunk_key = repo.chunks_for_source("lead-source")[0].chunk_key

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    source_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/sources",
        json={
            "sourceKey": "bls-laus",
            "sourceType": "dataset",
            "title": "BLS LAUS",
            "url": "https://example.com/bls.csv",
            "publisher": "BLS",
            "accessDate": "2026-05-14T00:00:00Z",
            "accessMethod": "api",
            "freshnessStatus": "fresh",
        },
    )
    assert source_resp.status_code == 200
    assert source_resp.json()["source_key"] == "bls-laus"
    assert source_resp.json()["sourceState"]["isFresh"] is True

    claim_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/claims",
        json={
            "claimKey": "claim-001",
            "statement": "Unemployment fell after 2021.",
            "artifactPath": "artifacts/report.md",
            "status": "supported",
            "evidencePaths": ["topics/labor/notes.md"],
            "evidenceChunkKeys": [chunk_key],
            "sourceKeys": ["bls-laus", "lead-source"],
            "contradictsClaimKeys": ["claim-002"],
            "openQuestions": ["Does the same pattern hold for neighboring counties?"],
        },
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["source_keys"] == ["bls-laus", "lead-source"]
    assert claim_resp.json()["evidence_chunk_keys"] == [chunk_key]
    assert claim_resp.json()["contradicts_claim_keys"] == ["claim-002"]
    assert claim_resp.json()["open_questions"] == ["Does the same pattern hold for neighboring counties?"]
    assert claim_resp.json()["claimState"]["openQuestionCount"] == 1

    artifact_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts",
        json={
            "artifactPath": "artifacts/report.md",
            "artifactType": "report",
            "title": "Report",
            "promotionState": "draft",
            "inputs": ["topics/data.csv"],
            "scripts": ["topics/analyze.py"],
            "verificationCommands": ["scripts/run-verification.sh"],
            "sources": ["research_plan/state/sources.json#bls-laus"],
            "claims": ["research_plan/state/claims.json#claim-001"],
            "verificationRuns": ["research_plan/state/verification_runs.json#run-001"],
        },
    )
    assert artifact_resp.status_code == 200
    assert artifact_resp.json()["verification_commands"] == ["scripts/run-verification.sh"]


async def test_patch_source_returns_dependents_and_marks_them_stale(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.patch(
        "/api/v1/projects/integrity-router-project/integrity/sources/bls-laus",
        json={"freshnessStatus": "stale", "qualityNotes": "Upstream data changed."},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"]["freshness_status"] == "stale"
    assert payload["affectedClaims"][0]["claim_key"] == "claim-001"
    assert payload["affectedArtifacts"][0]["artifact_path"] == "artifacts/report.md"

    detail = await client.get("/api/v1/projects/integrity-router-project/integrity/sources/bls-laus")
    assert detail.status_code == 200
    assert detail.json()["dependentClaims"][0]["status"] == "stale"


async def test_claim_detail_and_stale_graph_endpoints_return_dependency_views(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "bls-laus",
            "source_type": "dataset",
            "title": "BLS LAUS",
            "url_or_path": "https://example.com/bls.csv",
            "freshness_status": "stale",
            "provenance": {"text": "BLS extract about unemployment."},
        }
    )
    chunk_key = repo.chunks_for_source("bls-laus")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "evidence_chunk_keys": [chunk_key],
                "source_keys": ["bls-laus"],
                "status": "stale",
                "caveats": ["Seasonal adjustment may revise the series."],
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "claims": ["research_plan/state/claims.json#claim-001"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "stale_reasons": ["source_changed:bls-laus"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "scope": "artifact",
                "loop_type": "analysis_reproducibility",
                "status": "passed",
                "artifacts_checked": ["artifacts/report.md"],
                "claims_checked": ["claim-001"],
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    claim_resp = await client.get("/api/v1/projects/integrity-router-project/integrity/claims/claim-001")
    assert claim_resp.status_code == 200
    claim_payload = claim_resp.json()
    assert claim_payload["claim"]["claim_key"] == "claim-001"
    assert claim_payload["claim"]["caveats"] == ["Seasonal adjustment may revise the series."]
    assert claim_payload["sources"][0]["source_key"] == "bls-laus"
    assert claim_payload["chunks"][0]["chunk_key"] == chunk_key
    assert claim_payload["claimState"]["evidenceComplete"] is True
    assert claim_payload["verificationRuns"][0]["run_id"] == "run-001"

    graph_resp = await client.get("/api/v1/projects/integrity-router-project/integrity/stale-graph")
    assert graph_resp.status_code == 200
    graph_payload = graph_resp.json()
    edge_pairs = {(edge["from"], edge["to"]) for edge in graph_payload["edges"]}
    assert ("source:bls-laus", "claim:claim-001") in edge_pairs
    assert ("claim:claim-001", "artifact:artifacts/report.md") in edge_pairs

    lineage_resp = await client.get("/api/v1/projects/integrity-router-project/integrity/artifact-lineage")
    assert lineage_resp.status_code == 200
    assert lineage_resp.json()["artifactLineage"][0]["artifact_path"] == "artifacts/report.md"

    verification_resp = await client.get("/api/v1/projects/integrity-router-project/integrity/verification-runs")
    assert verification_resp.status_code == 200
    verification_payload = verification_resp.json()
    assert verification_payload["summary"]["count"] == 1
    assert verification_payload["summary"]["loopTypeCounts"]["analysis_reproducibility"] == 1
    assert verification_payload["verificationRuns"][0]["run_id"] == "run-001"

    benchmark_resp = await client.get("/api/v1/projects/integrity-router-project/integrity/benchmark?retrievalLimit=5")
    assert benchmark_resp.status_code == 200
    benchmark_payload = benchmark_resp.json()
    assert benchmark_payload["summary"]["caseCount"] == 7
    assert benchmark_payload["summary"]["passedCases"] == 7
    assert benchmark_payload["summary"]["hybridOutperformsVectorOnly"] is True


async def test_integrity_retrieval_endpoint_returns_explicit_and_semantic_results(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS Labor Force Data",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
            {
                "source_key": "lead-note",
                "source_type": "document",
                "title": "Regional labor lead note",
                "url_or_path": "topics/lead.md",
                "origin": "Internal",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "manual",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-supported",
                "claim_text": "Labor market unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            },
            {
                "claim_key": "claim-lead",
                "claim_text": "A similar labor pattern may exist in nearby regions.",
                "artifact_path": "artifacts/report.md",
                "source_keys": ["lead-note"],
                "status": "supported",
                "evidence_kind": "semantic_suggestion",
            },
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Labor Report",
                "promotion_state": "draft",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": [
                    "research_plan/state/sources.json#bls-laus",
                    "research_plan/state/sources.json#lead-note",
                ],
                "claims": [
                    "research_plan/state/claims.json#claim-supported",
                    "research_plan/state/claims.json#claim-lead",
                ],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "checks": [],
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get(
        "/api/v1/projects/integrity-router-project/integrity/retrieve",
        params={"q": "labor unemployment report", "limit": 6},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["summary"]["explicitEvidenceCount"] >= 1
    assert payload["summary"]["semanticSuggestionCount"] >= 1
    claim_results = {item["recordKey"]: item for item in payload["results"] if item["recordType"] == "claim"}
    assert claim_results["claim-supported"]["resultType"] == "explicit_evidence"
    assert claim_results["claim-lead"]["resultType"] == "semantic_suggestion"

    promote_resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "partially_verified"},
    )

    assert promote_resp.status_code == 200
    promote_payload = promote_resp.json()
    assert promote_payload["status"] == "blocked"
    assert "claim-lead" in promote_payload["gate"]["blockingClaims"]


async def test_source_detail_endpoint_returns_chunks(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {
                "text": "This briefing discusses interconnection queues and congestion in the regional grid."
            },
        }
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get("/api/v1/projects/integrity-router-project/integrity/sources/briefing-note")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["chunks"]
    assert payload["chunks"][0]["source_key"] == "briefing-note"
    assert payload["sourceState"]["isFresh"] is True


async def test_artifact_detail_endpoint_returns_trust_state(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get("/api/v1/projects/integrity-router-project/integrity/artifacts/artifacts/report.md")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["artifact"]["artifact_path"] == "artifacts/report.md"
    assert payload["trustState"]["currentState"] == "verified"
    assert payload["trustState"]["isTrusted"] is True
    assert payload["claims"][0]["claim_key"] == "claim-001"


async def test_integrity_graph_endpoint_returns_explicit_edges(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.upsert_source(
        {
            "source_key": "briefing-note",
            "source_type": "document",
            "title": "Briefing Note",
            "url_or_path": "topics/briefing.md",
            "origin": "Internal",
            "acquired_at": "2026-05-14T00:00:00Z",
            "access_method": "manual",
            "freshness_status": "fresh",
            "quality_status": "validated",
            "provenance": {"text": "Congestion increased queue delays in the region."},
        }
    )
    chunk_key = repo.chunks_for_source("briefing-note")[0].chunk_key
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Queue delays increased after congestion worsened.",
                "artifact_path": "artifacts/report.md",
                "evidence_chunk_keys": [chunk_key],
                "source_keys": ["briefing-note"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "scripts": ["topics/analyze.py"],
                "sources": ["research_plan/state/sources.json#briefing-note"],
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get("/api/v1/projects/integrity-router-project/integrity/graph")

    assert resp.status_code == 200
    payload = resp.json()
    relationships = {(item["from"], item["to"], item["relationship"]) for item in payload["edges"]}
    assert ("source:briefing-note", f"chunk:{chunk_key}", "chunked_as") in relationships
    assert ("source:briefing-note", "claim:claim-001", "supports") in relationships
    assert ("claim:claim-001", "artifact:artifacts/report.md", "supports") in relationships


async def test_integrity_graph_endpoint_exposes_dataset_nodes(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": ".ontology/onto.duckdb",
                "artifact_type": "dataset",
                "title": "Hydrated Dataset",
                "promotion_state": "verified",
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "scripts": ["pipelines/hydrate.py"],
            },
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
                "inputs": [".ontology/onto.duckdb"],
            },
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get("/api/v1/projects/integrity-router-project/integrity/graph")

    assert resp.status_code == 200
    payload = resp.json()
    node_types = {item["id"]: item["type"] for item in payload["nodes"]}
    relationships = {(item["from"], item["to"], item["relationship"]) for item in payload["edges"]}
    assert node_types["dataset:.ontology/onto.duckdb"] == "dataset"
    assert ("artifact:artifacts/report.md", "dataset:.ontology/onto.duckdb", "depends_on") in relationships


async def test_reproducibility_rerun_endpoint_updates_verification_and_artifact_state(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    artifact_path = root / "artifacts" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("stable report\n", encoding="utf-8")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "stale",
                "inputs": [".ontology/onto.duckdb"],
                "scripts": ["topics/analyze.py"],
                "verification_runs": [],
                "stale_reasons": ["source_changed:sample"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/reproducibility-rerun",
        json={"outputs": {"artifacts/report.md": "stable report\n"}, "runId": "rerun-001", "scope": "health"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "passed"
    assert payload["verificationRun"]["run_id"] == "rerun-001"
    updated = ResearchIntegrityRepo(root).load_artifact_lineage()[0]
    assert updated.promotion_state == "partially_verified"


async def test_freshness_evaluate_endpoint_applies_policy_and_returns_changes(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "api-source",
                "source_type": "api",
                "title": "API Source",
                "url_or_path": "https://example.com/api",
                "origin": "Provider",
                "acquired_at": "2026-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/freshness-evaluate",
        json={"asOf": "2026-05-14T00:00:00Z"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["changedSources"][0]["source"]["source_key"] == "api-source"
    assert payload["changedSources"][0]["nextStatus"] == "stale"


async def test_integrity_retrieval_endpoint_accepts_date_filters(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "older-source",
                "source_type": "dataset",
                "title": "Older Source",
                "url_or_path": "https://example.com/older.csv",
                "origin": "BLS",
                "acquired_at": "2024-01-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
            {
                "source_key": "recent-source",
                "source_type": "dataset",
                "title": "Recent Source",
                "url_or_path": "https://example.com/recent.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-01T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
            },
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.get(
        "/api/v1/projects/integrity-router-project/integrity/retrieve",
        params={
            "q": "source",
            "dateFrom": "2026-01-01T00:00:00Z",
            "dateTo": "2026-12-31T23:59:59Z",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    result_keys = {item["recordKey"] for item in payload["results"] if item["recordType"] == "source"}
    assert "recent-source" in result_keys
    assert "older-source" not in result_keys
    assert payload["filters"]["dateFrom"] == "2026-01-01T00:00:00Z"


async def test_artifact_promotion_endpoint_updates_promotion_state(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_sources(
        [
            {
                "source_key": "bls-laus",
                "source_type": "dataset",
                "title": "BLS LAUS",
                "url_or_path": "https://example.com/bls.csv",
                "origin": "BLS",
                "acquired_at": "2026-05-14T00:00:00Z",
                "access_method": "api",
                "freshness_status": "fresh",
                "quality_status": "validated",
                "provenance": {"text": "BLS extract."},
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unemployment fell after 2021.",
                "artifact_path": "artifacts/report.md",
                "evidence_paths": ["topics/labor/notes.md"],
                "source_keys": ["bls-laus"],
                "status": "supported",
                "evidence_kind": "direct",
            }
        ]
    )
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "partially_verified",
                "inputs": ["topics/data.csv"],
                "scripts": ["topics/analyze.py"],
                "verification_commands": ["scripts/run-verification.sh"],
                "sources": ["research_plan/state/sources.json#bls-laus"],
                "claims": ["research_plan/state/claims.json#claim-001"],
                "verification_runs": ["research_plan/state/verification_runs.json#run-001"],
            }
        ]
    )
    repo.write_verification_runs(
        [
            {
                "run_id": "run-001",
                "status": "passed",
                "artifact_paths": ["artifacts/report.md"],
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "verified"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "promoted"
    assert payload["artifact"]["promotion_state"] == "verified"


async def test_artifact_promotion_endpoint_returns_blocked_when_gate_fails(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "draft",
                "claims": ["research_plan/state/claims.json#claim-001"],
            }
        ]
    )
    repo.write_claims(
        [
            {
                "claim_key": "claim-001",
                "claim_text": "Unsupported claim.",
                "artifact_path": "artifacts/report.md",
                "status": "needs_evidence",
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "partially_verified"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "blocked"
    assert payload["artifact"]["promotion_state"] == "draft"
    assert payload["gate"]["blocked"] is True


async def test_artifact_promotion_endpoint_rejects_invalid_transition(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")
    repo = ResearchIntegrityRepo(root)
    repo.write_artifact_lineage(
        [
            {
                "artifact_path": "artifacts/report.md",
                "artifact_type": "report",
                "title": "Report",
                "promotion_state": "verified",
            }
        ]
    )

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/report.md", "targetState": "draft"},
    )

    assert resp.status_code == 400
    assert "Invalid promotion transition" in resp.json()["detail"]


async def test_artifact_promotion_endpoint_returns_404_for_missing_artifact(client, convex_mock, tmp_path):
    root = bootstrap_future_project(tmp_path, name="Integrity Router Project", slug="integrity-router-project")

    def _query(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload.get("path") in ("projects:get", "projects:getBySlug"):
            return httpx.Response(
                200,
                json={
                    "value": {
                        "_id": "project-id",
                        "name": "Integrity Router Project",
                        "slug": "integrity-router-project",
                        "status": "ready",
                        "localRepoPath": str(root),
                    }
                },
            )
        return httpx.Response(200, json={"value": None})

    convex_mock.post("/api/query").mock(side_effect=_query)

    resp = await client.post(
        "/api/v1/projects/integrity-router-project/integrity/artifacts/promote",
        json={"artifactPath": "artifacts/missing.md", "targetState": "verified"},
    )

    assert resp.status_code == 404
    assert "artifacts/missing.md" in resp.json()["detail"]
