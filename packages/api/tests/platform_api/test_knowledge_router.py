from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

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
    QueryRequest,
    QueryResult,
    SourceCheck,
    SourceImpact,
    SourceInventory,
    SourceRecord,
    Workflow,
    WorkflowInventory,
    WorkflowValidation,
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

    def query(self, project: ProjectRef, request: QueryRequest) -> QueryResult:
        self._record("query", project, request)
        return QueryResult(columns=["answer"], rows=[[42]], limit=request.limit)

    def workflows(self, project: ProjectRef) -> WorkflowInventory:
        self._record("workflows", project)
        return WorkflowInventory(workflows=[Workflow(id="research", path="workflows/research.yaml", valid=True, steps=2)])

    def workflow(self, project: ProjectRef, workflow_id: str) -> Workflow:
        self._record("workflow", project, workflow_id)
        return Workflow(id=workflow_id, path=f"workflows/{workflow_id}.yaml", valid=True, steps=2, metadata={"retries": 1})

    def validate_workflow(self, project: ProjectRef, workflow_id: str) -> WorkflowValidation:
        self._record("validate_workflow", project, workflow_id)
        return WorkflowValidation(workflow_id=workflow_id, valid=True, warnings=["uses fixture runner"])

    def approvals(self, project: ProjectRef) -> ApprovalInventory:
        self._record("approvals", project)
        return ApprovalInventory(approvals=[Approval(id="approval:one", status="pending")])

    def approval(self, project: ProjectRef, approval_id: str) -> Approval:
        self._record("approval", project, approval_id)
        return Approval(id=approval_id, status="pending", description="Review this")

    def decide_approval(self, project: ProjectRef, approval_id: str, decision) -> Approval:
        self._record("decide_approval", project, decision)
        return Approval(id=approval_id, status=decision.decision, description=decision.comment)


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
    client = TestClient(app)
    registered = client.post(
        "/api/v1/projects",
        json={"projectId": "fixture-id", "displayName": "Fixture", "path": str(project), "workspaceMode": "linked_local"},
    )
    assert registered.status_code == 201
    return client, runtime, project.resolve()


def _writable_client(tmp_path: Path) -> tuple[TestClient, FakeCanonicalRuntime]:
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    project = linked_root / "write-project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(project), "config", "user.name", "Test"], check=True)
    (project / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "commit", "-qm", "fixture"], check=True)
    runtime = FakeCanonicalRuntime()
    app = create_app(
        registry_config=RegistryConfig(tmp_path / "registry.json", tmp_path / "managed", (linked_root,)),
        runtime=runtime,
    )
    client = TestClient(app)
    assert client.post(
        "/api/v1/projects",
        json={"projectId": "write-id", "displayName": "Write", "path": str(project), "workspaceMode": "linked_local"},
    ).status_code == 201
    return client, runtime


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

    query = client.post("/api/v1/projects/fixture-id/query", json={"sql": "SELECT 42", "limit": 10})
    assert query.json()["result"] == {"columns": ["answer"], "rows": [[42]], "limit": 10, "truncated": False}

    assert client.get("/api/v1/projects/fixture-id/graph?entityType=person&limit=2").status_code == 200
    assert client.get("/api/v1/projects/fixture-id/sources").status_code == 200
    assert client.post("/api/v1/projects/fixture-id/sources/check").json()["check"]["status"] == "current"
    affected = client.get("/api/v1/projects/fixture-id/sources/affected?sourceId=src:one&sourceId=src:two")
    assert affected.json()["impact"] == {"source_ids": ["src:one", "src:two"], "documents": ["docs/one.md"]}
    assert client.get("/api/v1/projects/fixture-id/integrity").json()["integrity"]["claims"] == 2
    assert client.get("/api/v1/projects/fixture-id/workflows").json()["inventory"]["workflows"][0]["id"] == "research"
    assert client.get("/api/v1/projects/fixture-id/workflows/research").json()["workflow"]["metadata"] == {"retries": 1}
    assert client.post("/api/v1/projects/fixture-id/workflows/research/validate").json()["validation"]["warnings"] == ["uses fixture runner"]
    assert client.get("/api/v1/projects/fixture-id/approvals").status_code == 200
    assert client.get("/api/v1/projects/fixture-id/approvals/approval:one").json()["approval"]["id"] == "approval:one"

    operations = [operation for operation, _, _ in runtime.calls]
    assert operations == [
        "doctor", "find", "query", "graph", "sources", "check_sources", "affected_sources",
        "integrity", "workflows", "workflow", "validate_workflow", "approvals", "approval",
    ]
    for operation, project, _ in runtime.calls:
        assert project.project_id == "fixture-id", operation
        assert project.path == canonical_path, operation
        assert project.read_only is True, operation
    assert runtime.calls[1][2] == FindQuery(text="rail", types=["document"], topic="platform", explain=True)
    assert runtime.calls[2][2] == QueryRequest(sql="SELECT 42", limit=10)
    assert runtime.calls[3][2] == GraphQuery(entity_type="person", limit=2)
    assert runtime.calls[6][2] == ["src:one", "src:two"]


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


def test_approval_decision_fails_closed_for_read_only_projects(tmp_path: Path):
    client, runtime, _ = _client(tmp_path)
    response = client.post(
        "/api/v1/projects/fixture-id/approvals/approval:one/decision",
        json={"decision": "approved", "resume": True},
        headers={"X-Request-ID": "approval-denied"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "project_read_only"
    assert response.headers["X-Request-ID"] == "approval-denied"
    assert [call[0] for call in runtime.calls] == ["doctor"]


def test_approval_decision_uses_the_canonical_runtime_for_writable_projects(tmp_path: Path):
    client, runtime = _writable_client(tmp_path)
    response = client.post(
        "/api/v1/projects/write-id/approvals/approval:one/decision",
        json={"decision": "changes_requested", "comment": "add evidence", "resume": True},
    )
    assert response.status_code == 200
    assert response.json()["approval"] == {
        "id": "approval:one", "status": "changes_requested", "description": "add evidence",
        "workflow_run_id": None, "workflow_step_id": None, "metadata": {},
    }
    assert runtime.calls[-1][0] == "decide_approval"
    assert runtime.calls[-1][2].decision == "changes_requested"
    assert runtime.calls[-1][2].resume is True
