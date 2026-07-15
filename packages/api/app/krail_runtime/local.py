"""Local implementation of the RAIL-owned KRAIL runtime boundary."""

from __future__ import annotations

from importlib import import_module, metadata
from pathlib import Path
from typing import Any

from .contracts import (
    Approval,
    ApprovalDecision,
    ApprovalInventory,
    CapabilityGap,
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
    RunHandle,
    RunRequest,
    SourceInventory,
    SourceCheck,
    SourceImpact,
    SourceRecord,
    Workflow,
    WorkflowInventory,
    WorkflowValidation,
)
from .errors import (
    KrailCapabilityGapError,
    KrailPermissionError,
    KrailProjectNotFoundError,
    KrailRecordNotFoundError,
    KrailRuntimeError,
    KrailShadowingError,
    KrailUnavailableError,
    KrailValidationError,
)


class LocalKrailRuntime:
    """Adapter over the published ``krail`` distribution's ``rail`` namespace."""

    supported_version = "0.2.2"

    def capability_gaps(self) -> list[CapabilityGap]:
        return [
            CapabilityGap(
                operation="sql_hydration_requirement",
                reason="KRAIL's SQL helper depends on a hydrated ontology artifact; the small markdown fixture has none.",
                workaround="Hydrate an ontology pipeline before querying; the adapter uses KRAIL's public Project.query method.",
            ),
            CapabilityGap(
                operation="workflow_process_control",
                reason="KRAIL executes locally and does not provide platform process cancellation or event streaming.",
                workaround="M4 owns isolated execution, cancellation, and live-event normalization.",
            ),
            CapabilityGap(
                operation="integrity_status",
                reason="KRAIL 0.2.2 routes Project.integrity_status through retired RAIL service modules in local mode.",
                workaround="This adapter uses KRAIL's public ResearchIntegrityRepo record API until upstream provides a local summary method.",
            ),
            CapabilityGap(
                operation="project_initialization",
                reason="KRAIL 0.2.2 has no Python project-initialization API.",
                workaround="Managed workspaces use the published `krail init` CLI through the server-owned, no-shell compatibility boundary.",
            ),
        ]

    def _rail(self):
        """Load KRAIL and reject a checkout of the retired in-repo rail package."""
        try:
            installed_version = metadata.version("krail")
        except metadata.PackageNotFoundError as exc:
            raise KrailUnavailableError(
                "The published krail distribution is not installed.", operation="load", cause=exc
            ) from exc
        if installed_version != self.supported_version:
            raise KrailUnavailableError(
                f"Unsupported krail version {installed_version!r}; expected {self.supported_version!r}.",
                operation="load",
            )
        rail = import_module("rail")
        module_path = Path(getattr(rail, "__file__", "")).resolve()
        distribution_root = Path(metadata.distribution("krail").locate_file("rail")).resolve()
        if not module_path.is_relative_to(distribution_root):
            raise KrailShadowingError(
                f"rail resolved to {module_path}, not the published krail distribution at {distribution_root}.",
                operation="load",
            )
        if getattr(rail, "__version__", None) != self.supported_version:
            raise KrailShadowingError(
                "The imported rail namespace does not report the pinned krail version.", operation="load"
            )
        return rail

    @staticmethod
    def _path(project: ProjectRef) -> Path:
        path = project.path.expanduser().resolve()
        if not path.is_dir():
            raise KrailProjectNotFoundError(f"Project directory does not exist: {path}", operation="open")
        return path

    def _open(self, project: ProjectRef):
        path = self._path(project)
        rail = self._rail()
        try:
            return rail.local(str(path))
        except Exception as exc:  # upstream exceptions are deliberately not part of our public contract
            raise self._translate(exc, operation="open") from exc

    @staticmethod
    def _require_write(project: ProjectRef, *, operation: str) -> None:
        if project.read_only:
            raise KrailPermissionError(
                "The registered project is read-only.",
                operation=operation,
            )

    @staticmethod
    def _translate(exc: Exception, *, operation: str) -> KrailRuntimeError:
        name = type(exc).__name__
        if isinstance(exc, FileNotFoundError):
            return KrailRecordNotFoundError(str(exc), operation=operation, cause=exc)
        if isinstance(exc, PermissionError):
            return KrailPermissionError(str(exc), operation=operation, cause=exc)
        if name in {"ManifestValidationError", "ValidationError", "ContractViolation"}:
            return KrailValidationError(str(exc), operation=operation, cause=exc)
        return KrailRuntimeError(str(exc) or name, operation=operation, cause=exc)

    @staticmethod
    def _call(operation: str, fn):
        try:
            return fn()
        except KrailRuntimeError:
            raise
        except Exception as exc:
            raise LocalKrailRuntime._translate(exc, operation=operation) from exc

    def doctor(self, project: ProjectRef) -> ProjectHealth:
        result = self._call("doctor", lambda: self._open(project).doctor())
        checks = [
            ProjectHealthCheck(name=str(item.get("name", "unknown")), ok=bool(item.get("ok")), detail=str(item.get("detail", "")))
            for item in result.get("checks", [])
            if isinstance(item, dict)
        ]
        warnings = [str(item.get("detail", item)) for item in result.get("warnings", [])]
        return ProjectHealth(ok=bool(result.get("ok")), checks=checks, warnings=warnings, krail_version=self.supported_version)

    def manifest(self, project: ProjectRef) -> ProjectManifest:
        rail = self._rail()
        try:
            manifest = rail.load_manifest(self._path(project))
        except KrailRuntimeError:
            raise
        except Exception as exc:
            # ``load_manifest`` currently exposes plain ValueError instances for
            # schema failures. Keep that upstream detail behind our stable
            # validation contract.
            raise KrailValidationError(
                str(exc) or "Invalid KRAIL project manifest.",
                operation="manifest",
                cause=exc,
            ) from exc
        return ProjectManifest(
            version=manifest.version,
            slug=manifest.project.slug,
            name=manifest.project.name,
            default_branch=manifest.project.default_branch,
            knowledge_mode=manifest.project.knowledge_mode,
            paths=manifest.paths.model_dump(),
        )

    def find(self, project: ProjectRef, query: FindQuery) -> FindResult:
        result = self._call(
            "find",
            lambda: self._open(project).find(
                query.text,
                limit=query.limit,
                types=query.types or None,
                topic=query.topic,
                entity=query.entity,
                status=query.status,
                freshness=query.freshness,
                workflow=query.workflow,
                explain=query.explain,
                rag=False,
            ),
        )
        raw_items = result.get("results", [])
        items = [self._find_item(item, index) for index, item in enumerate(raw_items) if isinstance(item, dict)]
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        return FindResult(
            query=str(result.get("query", query.text)),
            items=items,
            total=int(summary.get("total", len(items))),
            facets=result.get("facets") if isinstance(result.get("facets"), dict) else {},
            explanation=result.get("explain") if isinstance(result.get("explain"), dict) else None,
        )

    @staticmethod
    def _find_item(item: dict[str, Any], index: int) -> FindItem:
        identifier = str(item.get("id") or item.get("path") or item.get("key") or f"find:{index}")
        title = str(item.get("title") or item.get("name") or item.get("path") or identifier)
        known = {"id", "path", "key", "title", "name", "type", "score", "snippet"}
        return FindItem(
            id=identifier,
            kind=str(item.get("type") or "record"),
            title=title,
            path=str(item["path"]) if item.get("path") is not None else None,
            score=float(item["score"]) if item.get("score") is not None else None,
            snippet=str(item["snippet"]) if item.get("snippet") is not None else None,
            metadata={key: value for key, value in item.items() if key not in known},
        )

    def graph(self, project: ProjectRef, query: GraphQuery) -> GraphResult:
        opened = self._open(project)
        graph = self._call("graph", lambda: opened.graph_build(write=False))
        nodes = [
            GraphNode(
                id=str(item.get("id")),
                label=str(item.get("label") or item.get("id")),
                kind=str(item.get("nodeType") or "node"),
                metadata={key: value for key, value in item.items() if key not in {"id", "label", "nodeType"}},
            )
            for item in graph.get("nodes", [])
            if isinstance(item, dict)
        ]
        if query.entity_type:
            nodes = [node for node in nodes if node.metadata.get("entityType") == query.entity_type]
        edges = [
            GraphEdge(
                id=str(item.get("id")), source=str(item.get("from")), target=str(item.get("to")), relation=str(item.get("type")),
                metadata={key: value for key, value in item.items() if key not in {"id", "from", "to", "type"}},
            )
            for item in graph.get("edges", [])
            if isinstance(item, dict)
        ]
        if query.entity:
            entity_id = f"entity:{query.entity.lower().replace(' ', '-')}"
            edges = [edge for edge in edges if entity_id in {edge.source, edge.target}]
        if query.relation_type:
            edges = [edge for edge in edges if edge.relation == query.relation_type]
        documents = [
            GraphDocument(
                id=str(item.get("id")), path=str(item.get("path")), title=str(item.get("title") or item.get("path")),
                kind=str(item.get("kind") or "document"), topics=[str(value) for value in item.get("topics", [])],
                entities=[str(value) for value in item.get("entities", [])],
            )
            for item in graph.get("documents", [])
            if isinstance(item, dict)
        ]
        if query.topic:
            documents = [doc for doc in documents if query.topic in doc.topics]
        return GraphResult(
            nodes=nodes[: query.limit], edges=edges[: query.limit], documents=documents[: query.limit],
            counts={str(key): int(value) for key, value in (graph.get("counts") or {}).items() if isinstance(value, int)},
            warnings=[str(item.get("warning", item)) for item in graph.get("warnings", [])],
        )

    def sources(self, project: ProjectRef) -> SourceInventory:
        result = self._call("sources", lambda: self._open(project).sources_list())
        sources = []
        for item in result.get("sources", []):
            if not isinstance(item, dict):
                continue
            known = {"id", "type", "url", "path", "documents"}
            sources.append(SourceRecord(
                id=str(item.get("id")), kind=str(item.get("type") or "unknown"), url=item.get("url"), path=item.get("path"),
                documents=[str(value) for value in item.get("documents", [])],
                metadata={key: value for key, value in item.items() if key not in known},
            ))
        return SourceInventory(manifest_path=result.get("manifest_path"), sources=sources)

    def check_sources(self, project: ProjectRef) -> SourceCheck:
        """Check source freshness without mutating the KRAIL snapshot file."""
        result = self._call("sources_check", lambda: self._open(project).sources_check(write=False))
        return SourceCheck(
            status=str(result.get("status") or "unknown"),
            changed_source_ids=[str(value) for value in result.get("changed_sources", [])],
            errors=[str(item.get("error", item)) for item in result.get("errors", [])],
        )

    def affected_sources(self, project: ProjectRef, source_ids: list[str] | None = None) -> SourceImpact:
        result = self._call("sources_affected", lambda: self._open(project).sources_affected(source_ids=source_ids))
        documents = [
            str(item.get("path")) for item in result.get("affected_documents", [])
            if isinstance(item, dict) and item.get("path")
        ]
        return SourceImpact(source_ids=[str(value) for value in result.get("changed_sources", [])], documents=documents)

    def integrity(self, project: ProjectRef) -> IntegritySummary:
        rail = self._rail()
        repo = self._call("integrity", lambda: rail.ResearchIntegrityRepo(self._path(project)))
        assumptions = self._call("integrity", repo.load_assumptions)
        sources = self._call("integrity", repo.load_sources)
        claims = self._call("integrity", repo.load_claims)
        artifacts = self._call("integrity", repo.load_artifact_lineage)
        verification_runs = self._call("integrity", repo.load_verification_runs)
        details = {
            "assumptions": [item.model_dump(mode="json") for item in assumptions],
            "sources": [item.model_dump(mode="json") for item in sources],
            "claims": [item.model_dump(mode="json") for item in claims],
            "artifact_lineage": [item.model_dump(mode="json") for item in artifacts],
            "verification_runs": [item.model_dump(mode="json") for item in verification_runs],
        }
        return IntegritySummary(
            status="available", sources=len(sources), claims=len(claims), assumptions=len(assumptions),
            artifacts=len(artifacts), verification_runs=len(verification_runs), details=details,
        )

    def query(self, project: ProjectRef, request: QueryRequest) -> QueryResult:
        """Query KRAIL's hydrated read-only artifact without owning a SQL engine."""
        sql = request.sql.strip()
        normalized = sql.lower()
        if ";" in sql or not (normalized.startswith("select") or normalized.startswith("with")):
            raise KrailValidationError(
                "Only a single read-only SELECT or WITH query is permitted.", operation="query"
            )
        opened = self._open(project)
        query = getattr(opened, "query", None)
        if not callable(query):
            raise KrailCapabilityGapError(
                "This KRAIL runtime does not expose local SQL querying.", operation="query"
            )
        # KRAIL owns the DuckDB connection and returns a DataFrame. The wrapper
        # adds only an HTTP response bound without owning or reimplementing SQL.
        bounded_sql = f"SELECT * FROM ({sql}) AS rail_platform_query LIMIT {request.limit + 1}"
        try:
            frame = self._call("query", lambda: query(bounded_sql))
        except KrailRuntimeError as exc:
            artifact = getattr(getattr(opened, "_backend", None), "artifact_duckdb_path", None)
            if artifact is not None and not Path(artifact).exists():
                raise KrailCapabilityGapError(
                    "SQL query is unavailable until KRAIL has a hydrated ontology artifact.", operation="query", cause=exc
                ) from exc
            raise
        if not hasattr(frame, "columns") or not callable(getattr(frame, "itertuples", None)):
            raise KrailRuntimeError("KRAIL returned an invalid SQL query result.", operation="query")
        columns = [str(value) for value in frame.columns]
        rows = [list(row) for row in frame.itertuples(index=False, name=None)]
        return QueryResult(columns=columns, rows=rows[:request.limit], limit=request.limit, truncated=len(rows) > request.limit)

    def workflows(self, project: ProjectRef) -> WorkflowInventory:
        opened = self._open(project)
        list_workflows = getattr(opened, "list_workflows", None)
        if not callable(list_workflows):
            raise KrailCapabilityGapError(
                "This KRAIL runtime does not expose workflow inventory.", operation="workflows"
            )
        result = self._call("workflows", list_workflows)
        workflows = []
        for item in result.get("specs", []):
            if isinstance(item, dict):
                workflows.append(Workflow(
                    id=str(item.get("id")), path=item.get("path"), valid=item.get("valid"), steps=item.get("steps"),
                    metadata={key: value for key, value in item.items() if key not in {"id", "path", "valid", "steps"}},
                ))
        return WorkflowInventory(workflows=workflows, pack=result.get("pack"), mode=result.get("mode"))

    def workflow(self, project: ProjectRef, workflow_id: str) -> Workflow:
        opened = self._open(project)
        show = getattr(opened, "workflow_show", None)
        if not callable(show):
            raise KrailCapabilityGapError(
                "This KRAIL runtime does not expose workflow detail.", operation="workflow_show"
            )
        result = self._call("workflow_show", lambda: show(workflow_id))
        item = result.get("workflow") if isinstance(result, dict) and isinstance(result.get("workflow"), dict) else result
        if not isinstance(item, dict):
            raise KrailRuntimeError("KRAIL returned an invalid workflow detail response.", operation="workflow_show")
        return self._workflow(item)

    def validate_workflow(self, project: ProjectRef, workflow_id: str) -> WorkflowValidation:
        opened = self._open(project)
        validate = getattr(opened, "workflow_validate", None)
        if not callable(validate):
            raise KrailCapabilityGapError(
                "This KRAIL runtime does not expose workflow validation.", operation="workflow_validate"
            )
        result = self._call("workflow_validate", lambda: validate(workflow_id))
        if not isinstance(result, dict):
            raise KrailRuntimeError("KRAIL returned an invalid workflow validation response.", operation="workflow_validate")
        errors = result.get("errors", [])
        warnings = result.get("warnings", [])
        return WorkflowValidation(
            workflow_id=str(result.get("workflow_id") or result.get("workflow") or workflow_id),
            valid=bool(result.get("valid")),
            errors=[str(item.get("message", item)) if isinstance(item, dict) else str(item) for item in errors],
            warnings=[str(item.get("message", item)) if isinstance(item, dict) else str(item) for item in warnings],
            details={key: value for key, value in result.items() if key not in {"workflow_id", "workflow", "valid", "errors", "warnings"}},
        )

    @staticmethod
    def _workflow(item: dict[str, Any]) -> Workflow:
        known = {"id", "workflow_id", "path", "valid", "steps", "status"}
        return Workflow(
            id=str(item.get("id") or item.get("workflow_id")), path=item.get("path"), valid=item.get("valid"),
            steps=item.get("steps"), status=item.get("status"),
            metadata={key: value for key, value in item.items() if key not in known},
        )

    def approvals(self, project: ProjectRef) -> ApprovalInventory:
        result = self._call("approvals", lambda: self._open(project).approval_list())
        return ApprovalInventory(approvals=[self._approval(item) for item in result.get("approvals", []) if isinstance(item, dict)])

    def approval(self, project: ProjectRef, approval_id: str) -> Approval:
        result = self._call("approval_show", lambda: self._open(project).approval_show(approval_id))
        return self._approval(result.get("approval") if isinstance(result, dict) else {})

    def decide_approval(self, project: ProjectRef, approval_id: str, decision: ApprovalDecision) -> Approval:
        self._require_write(project, operation="approval_decide")
        opened = self._open(project)
        decide = getattr(opened, "approval_decide", None)
        if not callable(decide):
            raise KrailCapabilityGapError(
                "This KRAIL runtime does not expose approval decisions.", operation="approval_decide"
            )
        result = self._call(
            "approval_decide",
            lambda: decide(approval_id, decision=decision.decision, comment=decision.comment, resume=decision.resume),
        )
        return self._approval(result.get("approval") if isinstance(result, dict) else result)

    @staticmethod
    def _approval(item: dict[str, Any]) -> Approval:
        known = {"approval_id", "_id", "status", "description", "workflow_run_id", "workflow_step_id"}
        return Approval(
            id=str(item.get("approval_id") or item.get("_id")), status=item.get("status"), description=item.get("description"),
            workflow_run_id=item.get("workflow_run_id"), workflow_step_id=item.get("workflow_step_id"),
            metadata={key: value for key, value in item.items() if key not in known},
        )

    def execute_workflow(self, project: ProjectRef, request: RunRequest) -> RunHandle:
        self._require_write(project, operation="execute_workflow")
        result = self._call(
            "execute_workflow",
            lambda: self._open(project).execute_workflow(
                request.workflow_id, dry_run=request.dry_run, force=request.force, inputs=request.inputs or None
            ),
        )
        return RunHandle(
            run_id=result.get("run_id"), workflow_id=str(result.get("workflow") or request.workflow_id),
            status=str(result.get("status") or "unknown"), pending_approval_id=result.get("pending_approval_id"), details=result,
        )
