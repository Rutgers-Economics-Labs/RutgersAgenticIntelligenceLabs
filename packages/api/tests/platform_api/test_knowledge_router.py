from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.v1.knowledge_router import router as knowledge_router
from app.krail_runtime.contracts import (
    Approval,
    ApprovalInventory,
    FindItem,
    FindQuery,
    FindResult,
    GraphDocument,
    GraphEdge,
    GraphNode,
    GraphQuery,
    GraphResult,
    IntegritySummary,
    ProjectHealth,
    ProjectHealthCheck,
    ProjectManifest,
    ProjectRef,
    SourceCheck,
    SourceImpact,
    SourceInventory,
    SourceRecord,
    Workflow,
    WorkflowInventory,
)
from app.main_krail import create_app
from app.projects.registry import RegistryConfig


class FakeCanonicalRuntime:
    """A fake of the canonical adapter, never a project-file substitute."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ProjectRef, object | None]] = []

    def _record(self, operation: str, project: ProjectRef, argument: object | None = None) -> None:
        self.calls.append((operation, project, argument))

    def doctor(self, project: ProjectRef) -> ProjectHealth:
        self._record("doctor", project)
        return ProjectHealth(
            ok=True,
            checks=[ProjectHealthCheck(name="manifest", ok=True, detail="valid")],
            krail_version="0.2.2",
        )

    def manifest(self, project: ProjectRef) -> ProjectManifest:
        return ProjectManifest(
            version=1, slug="fixture", name="Fixture", default_branch="main",
            knowledge_mode="markdown_graph", paths={},
        )

    def find(self, project: ProjectRef, query: FindQuery) -> FindResult:
        self._record("find", project, query)
        return FindResult(
            query=query.text,
            items=[FindItem(id="doc:one", kind="document", title="One", score=0.9)],
            total=1,
            explanation={"filters": {"topic": query.topic}} if query.explain else None,
        )

    def graph(self, project: ProjectRef, query: GraphQuery) -> GraphResult:
        self._record("graph", project, query)
        return GraphResult(
            nodes=[GraphNode(id="entity:one", label="One", kind="entity")],
            edges=[GraphEdge(id="edge:one", source="entity:one", target="doc:one", relation="mentions")],
            documents=[GraphDocument(id="doc:one", path="docs/one.md", title="One", kind="document")],
        )

    def sources(self, project: ProjectRef) -> SourceInventory:
        self._record("sources", project)
        return SourceInventory(sources=[SourceRecord(id="src:one", kind="web", url="https://example.test")])

    def check_sources(self, project: ProjectRef) -> SourceCheck:
        self._record("check_sources", project)
        return SourceCheck(status="current")

    def affected_sources(self, project: ProjectRef, source_ids: list[str] | None = None) -> SourceImpact:
        self._record("affected_sources", project, source_ids)
        return SourceImpact(source_ids=source_ids or [], documents=["docs/one.md"])

    def integrity(self, project: ProjectRef) -> IntegritySummary:
        self._record("integrity", project)
        return IntegritySummary(status="available", sources=1, claims=2)

    def workflows(self, project: ProjectRef) -> WorkflowInventory:
        self._record("workflows", project)
        return WorkflowInventory(workflows=[Workflow(id="research", path="workflows/research.yaml", valid=True, steps=2)])

    def approvals(self, project: ProjectRef) -> ApprovalInventory:
        self._record("approvals", project)
        return ApprovalInventory(approvals=[Approval(id="approval:one", status="pending")])

    def approval(self, project: ProjectRef, approval_id: str) -> Approval:
        self._record("approval", project, approval_id)
        return Approval(id=approval_id, status="pending", description="Review this")


def _client(tmp_path: Path) -> tuple[TestClient, FakeCanonicalRuntime, Path]:
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    project = linked_root / "read-only-project"
    project.mkdir()
    runtime = FakeCanonicalRuntime()
    app = create_app(
        registry_config=RegistryConfig(
            storage_path=tmp_path / "registry.json",
            managed_workspace_root=tmp_path / "managed",
            linked_workspace_roots=(linked_root,),
        ),
        runtime=runtime,
    )
    # M3 is deliberately isolated: M3's parent bootstrap wiring adds this router.
    app.include_router(knowledge_router, prefix="/api/v1")
    client = TestClient(app)
    registered = client.post(
        "/api/v1/projects",
        json={"projectId": "fixture-id", "displayName": "Fixture", "path": str(project), "workspaceMode": "linked_local"},
    )
    assert registered.status_code == 201
    return client, runtime, project.resolve()


def test_read_only_knowledge_routes_use_canonical_runtime_and_registry_ref(tmp_path: Path):
    client, runtime, canonical_path = _client(tmp_path)
    headers = {"X-Request-ID": "knowledge-request"}

    find = client.post(
        "/api/v1/projects/fixture-id/find",
        json={"text": "rail", "types": ["document"], "topic": "platform", "explain": True},
        headers=headers,
    )
    assert find.status_code == 200
    assert find.headers["X-Request-ID"] == "knowledge-request"
    assert find.json()["result"]["explanation"] == {"filters": {"topic": "platform"}}
    assert find.json()["result"]["items"][0] == {
        "id": "doc:one", "kind": "document", "title": "One", "path": None,
        "score": 0.9, "snippet": None, "metadata": {},
    }

    assert client.get("/api/v1/projects/fixture-id/graph?entityType=person&limit=2").status_code == 200
    assert client.get("/api/v1/projects/fixture-id/sources").status_code == 200
    assert client.post("/api/v1/projects/fixture-id/sources/check").json()["check"]["status"] == "current"
    affected = client.get("/api/v1/projects/fixture-id/sources/affected?sourceId=src:one&sourceId=src:two")
    assert affected.json()["impact"] == {"source_ids": ["src:one", "src:two"], "documents": ["docs/one.md"]}
    assert client.get("/api/v1/projects/fixture-id/integrity").json()["integrity"]["claims"] == 2
    assert client.get("/api/v1/projects/fixture-id/workflows").json()["inventory"]["workflows"][0]["id"] == "research"
    assert client.get("/api/v1/projects/fixture-id/approvals").status_code == 200
    assert client.get("/api/v1/projects/fixture-id/approvals/approval:one").json()["approval"]["id"] == "approval:one"

    operations = [operation for operation, _, _ in runtime.calls]
    assert operations == [
        "doctor", "find", "graph", "sources", "check_sources", "affected_sources",
        "integrity", "workflows", "approvals", "approval",
    ]
    for operation, project, _ in runtime.calls:
        assert project.project_id == "fixture-id", operation
        assert project.path == canonical_path, operation
        assert project.read_only is True, operation
    assert runtime.calls[1][2] == FindQuery(text="rail", types=["document"], topic="platform", explain=True)
    assert runtime.calls[2][2] == GraphQuery(entity_type="person", limit=2)
    assert runtime.calls[5][2] == ["src:one", "src:two"]


def test_knowledge_request_and_path_validation_remain_structured(tmp_path: Path):
    client, runtime, _ = _client(tmp_path)

    invalid_find = client.post("/api/v1/projects/fixture-id/find", json={"text": "", "limit": 101})
    assert invalid_find.status_code == 422
    assert invalid_find.json()["error"]["code"] == "request_validation_error"
    assert invalid_find.headers["X-Request-ID"] == invalid_find.json()["error"]["requestId"]

    invalid_source = client.get("/api/v1/projects/fixture-id/sources/affected?sourceId=")
    assert invalid_source.status_code == 422
    assert invalid_source.json()["error"]["code"] == "request_validation_error"
    invalid_approval = client.get("/api/v1/projects/fixture-id/approvals/" + ("x" * 201))
    assert invalid_approval.status_code == 422
    assert invalid_approval.json()["error"]["code"] == "request_validation_error"
    assert [call[0] for call in runtime.calls] == ["doctor"]
