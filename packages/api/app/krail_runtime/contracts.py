"""Versioned, RAIL-owned contracts for the KRAIL adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class RuntimeDTO(BaseModel):
    """Base DTO configured to reject accidental upstream response leakage."""

    model_config = ConfigDict(extra="forbid")


class ProjectRef(RuntimeDTO):
    """A resolved KRAIL project directory, supplied by the platform registry."""

    path: Path
    project_id: str | None = None
    read_only: bool = False

    @property
    def canonical_path(self) -> str:
        """Compatibility view for control-plane records and audit events."""
        return str(self.path)


class ProjectHealthCheck(RuntimeDTO):
    name: str
    ok: bool
    detail: str


class ProjectHealth(RuntimeDTO):
    ok: bool
    checks: list[ProjectHealthCheck]
    warnings: list[str] = Field(default_factory=list)
    krail_version: str


class ProjectManifest(RuntimeDTO):
    version: int
    slug: str
    name: str
    default_branch: str
    knowledge_mode: str
    paths: dict[str, str]


class FindQuery(RuntimeDTO):
    text: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    types: list[str] = Field(default_factory=list)
    topic: str | None = None
    entity: str | None = None
    status: str | None = None
    freshness: str | None = None
    workflow: str | None = None
    explain: bool = False


class FindItem(RuntimeDTO):
    id: str
    kind: str
    title: str
    path: str | None = None
    score: float | None = None
    snippet: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FindResult(RuntimeDTO):
    query: str
    items: list[FindItem]
    total: int
    facets: dict[str, Any] = Field(default_factory=dict)
    explanation: dict[str, Any] | None = None


class GraphQuery(RuntimeDTO):
    entity_type: str | None = None
    entity: str | None = None
    relation_type: str | None = None
    topic: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class GraphNode(RuntimeDTO):
    id: str
    label: str
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(RuntimeDTO):
    id: str
    source: str
    target: str
    relation: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphDocument(RuntimeDTO):
    id: str
    path: str
    title: str
    kind: str
    topics: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class GraphResult(RuntimeDTO):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    documents: list[GraphDocument]
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class SourceRecord(RuntimeDTO):
    id: str
    kind: str
    url: str | None = None
    path: str | None = None
    documents: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceInventory(RuntimeDTO):
    manifest_path: str | None = None
    sources: list[SourceRecord]


class SourceCheck(RuntimeDTO):
    status: str
    changed_source_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class SourceImpact(RuntimeDTO):
    source_ids: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)


class IntegritySummary(RuntimeDTO):
    status: str
    sources: int = 0
    claims: int = 0
    assumptions: int = 0
    artifacts: int = 0
    verification_runs: int = 0
    details: dict[str, Any] = Field(default_factory=dict)


class Workflow(RuntimeDTO):
    id: str
    path: str | None = None
    valid: bool | None = None
    steps: int | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowInventory(RuntimeDTO):
    workflows: list[Workflow]
    pack: str | None = None
    mode: str | None = None


class WorkflowValidation(RuntimeDTO):
    workflow_id: str
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class QueryRequest(RuntimeDTO):
    """A bounded, read-only SQL request for a hydrated KRAIL artifact."""

    sql: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=100, ge=1, le=1_000)


class QueryResult(RuntimeDTO):
    columns: list[str]
    rows: list[list[Any]]
    limit: int
    truncated: bool = False


class Approval(RuntimeDTO):
    id: str
    status: str | None = None
    description: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalInventory(RuntimeDTO):
    approvals: list[Approval]


class ApprovalDecision(RuntimeDTO):
    decision: Literal["approved", "rejected", "changes_requested"]
    comment: str = Field(default="", max_length=4_000)
    resume: bool = False


class RunRequest(RuntimeDTO):
    workflow_id: str = Field(min_length=1, max_length=200)
    dry_run: bool = True
    force: bool = False
    inputs: dict[str, Any] = Field(default_factory=dict)


class RunHandle(RuntimeDTO):
    run_id: str | None = None
    workflow_id: str
    status: str
    pending_approval_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CapabilityGap(RuntimeDTO):
    operation: str
    reason: str
    workaround: str | None = None


class KrailRuntime(Protocol):
    def doctor(self, project: ProjectRef) -> ProjectHealth: ...
    def manifest(self, project: ProjectRef) -> ProjectManifest: ...
    def find(self, project: ProjectRef, query: FindQuery) -> FindResult: ...
    def graph(self, project: ProjectRef, query: GraphQuery) -> GraphResult: ...
    def sources(self, project: ProjectRef) -> SourceInventory: ...
    def check_sources(self, project: ProjectRef) -> SourceCheck: ...
    def affected_sources(self, project: ProjectRef, source_ids: list[str] | None = None) -> SourceImpact: ...
    def integrity(self, project: ProjectRef) -> IntegritySummary: ...
    def query(self, project: ProjectRef, request: QueryRequest) -> QueryResult: ...
    def workflows(self, project: ProjectRef) -> WorkflowInventory: ...
    def workflow(self, project: ProjectRef, workflow_id: str) -> Workflow: ...
    def validate_workflow(self, project: ProjectRef, workflow_id: str) -> WorkflowValidation: ...
    def approvals(self, project: ProjectRef) -> ApprovalInventory: ...
    def approval(self, project: ProjectRef, approval_id: str) -> Approval: ...
    def decide_approval(
        self,
        project: ProjectRef,
        approval_id: str,
        decision: ApprovalDecision,
    ) -> Approval: ...
    def execute_workflow(self, project: ProjectRef, request: RunRequest) -> RunHandle: ...
