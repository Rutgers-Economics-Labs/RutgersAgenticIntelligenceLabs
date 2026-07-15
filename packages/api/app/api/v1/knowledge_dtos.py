"""RAIL-owned HTTP DTOs for read-only KRAIL knowledge endpoints.

The KRAIL adapter owns normalization of upstream data.  These models own the
versioned browser contract, including camel-case JSON field names.
"""
from __future__ import annotations

from pydantic import Field

from app.krail_runtime.contracts import (
    Approval,
    ApprovalInventory,
    FindQuery,
    FindResult,
    GraphQuery,
    GraphResult,
    IntegritySummary,
    SourceCheck,
    SourceImpact,
    SourceInventory,
    WorkflowInventory,
)

from .dtos import DTO


class FindRequest(DTO):
    text: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    types: list[str] = Field(default_factory=list, max_length=50)
    topic: str | None = Field(default=None, max_length=200)
    entity: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=100)
    freshness: str | None = Field(default=None, max_length=100)
    workflow: str | None = Field(default=None, max_length=200)
    explain: bool = False

    def to_runtime(self) -> FindQuery:
        return FindQuery.model_validate(self.model_dump(by_alias=False))


class GraphRequest(DTO):
    entity_type: str | None = Field(default=None, alias="entityType", max_length=100)
    entity: str | None = Field(default=None, max_length=200)
    relation_type: str | None = Field(default=None, alias="relationType", max_length=100)
    topic: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=100, ge=1, le=500)

    def to_runtime(self) -> GraphQuery:
        return GraphQuery.model_validate(self.model_dump(by_alias=False))


class FindResponse(DTO):
    project_id: str = Field(alias="projectId")
    result: FindResult

    @classmethod
    def from_runtime(cls, project_id: str, result: FindResult) -> "FindResponse":
        return cls(project_id=project_id, result=result)


class GraphResponse(DTO):
    project_id: str = Field(alias="projectId")
    graph: GraphResult

    @classmethod
    def from_runtime(cls, project_id: str, graph: GraphResult) -> "GraphResponse":
        return cls(project_id=project_id, graph=graph)


class SourceInventoryResponse(DTO):
    project_id: str = Field(alias="projectId")
    inventory: SourceInventory

    @classmethod
    def from_runtime(cls, project_id: str, inventory: SourceInventory) -> "SourceInventoryResponse":
        return cls(project_id=project_id, inventory=inventory)


class SourceCheckResponse(DTO):
    project_id: str = Field(alias="projectId")
    check: SourceCheck

    @classmethod
    def from_runtime(cls, project_id: str, check: SourceCheck) -> "SourceCheckResponse":
        return cls(project_id=project_id, check=check)


class SourceImpactResponse(DTO):
    project_id: str = Field(alias="projectId")
    impact: SourceImpact

    @classmethod
    def from_runtime(cls, project_id: str, impact: SourceImpact) -> "SourceImpactResponse":
        return cls(project_id=project_id, impact=impact)


class IntegrityResponse(DTO):
    project_id: str = Field(alias="projectId")
    integrity: IntegritySummary

    @classmethod
    def from_runtime(cls, project_id: str, integrity: IntegritySummary) -> "IntegrityResponse":
        return cls(project_id=project_id, integrity=integrity)


class WorkflowInventoryResponse(DTO):
    project_id: str = Field(alias="projectId")
    inventory: WorkflowInventory

    @classmethod
    def from_runtime(cls, project_id: str, inventory: WorkflowInventory) -> "WorkflowInventoryResponse":
        return cls(project_id=project_id, inventory=inventory)


class ApprovalInventoryResponse(DTO):
    project_id: str = Field(alias="projectId")
    inventory: ApprovalInventory

    @classmethod
    def from_runtime(cls, project_id: str, inventory: ApprovalInventory) -> "ApprovalInventoryResponse":
        return cls(project_id=project_id, inventory=inventory)


class ApprovalResponse(DTO):
    project_id: str = Field(alias="projectId")
    approval: Approval

    @classmethod
    def from_runtime(cls, project_id: str, approval: Approval) -> "ApprovalResponse":
        return cls(project_id=project_id, approval=approval)
