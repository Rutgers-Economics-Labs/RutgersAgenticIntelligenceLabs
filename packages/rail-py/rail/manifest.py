from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


HydrationMode = Literal["full", "incremental"]
RunnerName = Literal["jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli", "copilot_cli"]
PlannerThreadMode = Literal["project"]
IndexMode = Literal["filesystem"]
HomeView = Literal["planner", "project_home", "artifacts"]
WorkspaceMode = Literal["isolated"]
CheckpointMode = Literal["git-ref", "none"]
AutonomyMode = Literal["assisted", "supervised_autopilot", "autopilot"]
ProjectMode = Literal["ontology_first", "research_first"]
SourceOfTruth = Literal["git"]
QuestionClassification = Literal[
    "answerable_now",
    "answerable_after_requery",
    "answerable_after_expansion",
    "blocked_by_data",
]
AuditStage = Literal["session", "planner", "ontology", "integrity", "critic", "closeout"]


def _validate_repo_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("paths must be repository-relative, not absolute")
    if any(part == ".." for part in path.parts):
        raise ValueError("paths may not traverse outside the repository")
    return value


class ProjectSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    slug: str
    default_branch: str
    description: str | None = None
    git_repo_url: str | None = None
    agent_model: str | None = None
    mode: ProjectMode = "ontology_first"


class RepoContractSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_paths: list[str] = Field(
        default_factory=lambda: [".ontology", "specs", "research_plan", "topics", "agents", "skills"]
    )
    flexible_paths: list[str] = Field(default_factory=lambda: ["artifacts", "topics/**"])
    source_of_truth: SourceOfTruth = "git"

    @field_validator("required_paths", "flexible_paths")
    @classmethod
    def _validate_contract_paths(cls, values: list[str]) -> list[str]:
        return [_validate_repo_relative_path(value) for value in values]


class PathsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ontology_root: str = ".ontology"
    topics_root: str = "topics"
    specs_root: str = "specs"
    plan_root: str = "research_plan"
    agents_root: str = "agents"
    skills_root: str = "skills"
    artifacts_root: str = "artifacts"

    @field_validator(
        "ontology_root",
        "topics_root",
        "specs_root",
        "plan_root",
        "agents_root",
        "skills_root",
        "artifacts_root",
    )
    @classmethod
    def _validate_paths(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class HydrationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ontology_file: str
    sources_dir: str
    pipelines_dir: str
    transforms_dir: str | None = None
    default_pipeline: str | None = None
    linked_sources: list[str] = Field(default_factory=list)
    hydration_mode: HydrationMode = "full"

    @field_validator("ontology_file", "sources_dir", "pipelines_dir", "transforms_dir")
    @classmethod
    def _validate_relative_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_repo_relative_path(value)


class RunnerPolicySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: list[RunnerName] = Field(default_factory=list)
    preferred: list[RunnerName] = Field(default_factory=list)


class AgentsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles_dir: str = "agents"
    default_runner: RunnerName = "jules"
    runner_policy: RunnerPolicySection = Field(default_factory=RunnerPolicySection)
    sequential_execution: bool = True
    approval_required_for_write_runs: bool | None = None
    planner_thread_mode: PlannerThreadMode = "project"
    default_planner_role: str = "planner"

    @field_validator("roles_dir")
    @classmethod
    def _validate_roles_dir(cls, value: str) -> str:
        return _validate_repo_relative_path(value)

    @model_validator(mode="after")
    def _enforce_v1_constraints(self) -> "AgentsSection":
        if not self.sequential_execution:
            raise ValueError("V1 requires sequential_execution=true")
        return self


class AutonomySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AutonomyMode = "assisted"
    require_human_for: list[str] = Field(default_factory=list)
    allow_without_human: list[str] = Field(default_factory=list)
    max_runtime_minutes: int | None = Field(default=None, ge=1)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_retries_per_task: int | None = Field(default=None, ge=0)


class IntegritySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_synthetic_data: bool = False
    require_source_for_datasets: bool = True
    require_lineage_for_final_artifacts: bool = True
    require_evidence_for_report_claims: bool = True
    stale_outputs_block_promotion: bool = True


class FrontendSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_index_mode: IndexMode = "filesystem"
    artifact_index_mode: IndexMode = "filesystem"
    show_repo_tree: bool = True
    show_task_board_snapshot: bool = True
    default_home_view: HomeView = "project_home"


class WorkspacesSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: WorkspaceMode = "isolated"
    root: str = ".rail/workspaces"
    setup_script: str | None = "scripts/setup-workspace.sh"
    verification_script: str | None = "scripts/run-verification.sh"
    archive_script: str | None = "scripts/archive-workspace.sh"
    nonconcurrent_run: bool = True
    checkpoint_mode: CheckpointMode = "git-ref"

    @field_validator("root", "setup_script", "verification_script", "archive_script")
    @classmethod
    def _validate_relative_paths(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_repo_relative_path(value)


class ResearchQuestionPolicySection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_follow_up_generation: bool = True
    allow_midstream_direction_change: bool = True
    require_question_classification: bool = True
    allowed_classifications: list[QuestionClassification] = Field(
        default_factory=lambda: [
            "answerable_now",
            "answerable_after_requery",
            "answerable_after_expansion",
            "blocked_by_data",
        ]
    )


class ResearchSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_path: str = "topics/brief.md"
    spec_path: str = "specs/research_question.yaml"
    question_policy: ResearchQuestionPolicySection = Field(default_factory=ResearchQuestionPolicySection)

    @field_validator("brief_path", "spec_path")
    @classmethod
    def _validate_relative_paths(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class ResearchBurstSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_parallel: int = Field(default=1, ge=1, le=8)
    max_cost_usd: float | None = Field(default=None, ge=0)


class PlannerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_plan_path: str = "research_plan/current_plan.md"
    task_root: str = "research_plan/tasks"
    approval_root: str = "research_plan/approvals"
    decision_root: str = "research_plan/decisions"
    require_audit_before_advance: bool = True
    lane_policy: Literal["single_active_worker"] = "single_active_worker"

    @field_validator("current_plan_path", "task_root", "approval_root", "decision_root")
    @classmethod
    def _validate_relative_paths(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class AuditorsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    order: list[AuditStage] = Field(default_factory=lambda: ["session", "planner", "ontology", "integrity", "closeout"])
    fail_closed: bool = True


class VerificationSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deterministic_command: str = "scripts/run-verification.sh"
    require_integrity_gate_for: list[str] = Field(default_factory=lambda: ["artifact_generation", "closeout"])
    require_ontology_health_before: list[str] = Field(default_factory=lambda: ["research", "artifact"])
    required_artifact_lineage: bool = True
    required_claim_evidence: bool = True

    @field_validator("deterministic_command")
    @classmethod
    def _validate_command_path(cls, value: str) -> str:
        return _validate_repo_relative_path(value)


class SecretsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_scope: bool = True
    per_agent_allowlists: bool = True
    inject_at_session_start_only: bool = True
    allowed: dict[str, list[str]] = Field(default_factory=dict)


class ResearchSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    required_sources: list[str] = Field(default_factory=list)
    minimum_dataset: str | None = None
    output: str | None = None


class LifecycleSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phases: list[str] = Field(
        default_factory=lambda: [
            "brief",
            "scoped",
            "source_discovery",
            "config_ready",
            "hydration_ready",
            "hydrated",
            "ontology_healthy",
            "research_active",
            "synthesis_ready",
            "closed",
        ]
    )
    closeout_requires: list[str] = Field(
        default_factory=lambda: [
            "no_active_agents",
            "no_non_done_required_tasks",
            "clean_integrity_gate",
            "final_artifacts_present",
        ]
    )
    slices: dict[str, ResearchSlice] = Field(default_factory=dict)


class RailManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(..., ge=1)
    project: ProjectSection
    repo_contract: RepoContractSection = Field(default_factory=RepoContractSection)
    paths: PathsSection
    hydration: HydrationSection
    research: ResearchSection = Field(default_factory=ResearchSection)
    planner: PlannerSection = Field(default_factory=PlannerSection)
    agents: AgentsSection
    auditors: AuditorsSection = Field(default_factory=AuditorsSection)
    autonomy: AutonomySection = Field(default_factory=AutonomySection)
    integrity: IntegritySection = Field(default_factory=IntegritySection)
    verification: VerificationSection = Field(default_factory=VerificationSection)
    research_burst: ResearchBurstSection = Field(default_factory=ResearchBurstSection)
    secrets: SecretsSection = Field(default_factory=SecretsSection)
    lifecycle: LifecycleSection = Field(default_factory=LifecycleSection)
    workspaces: WorkspacesSection = Field(default_factory=WorkspacesSection)
    frontend: FrontendSection

    @model_validator(mode="after")
    def _validate_hydration_inside_ontology_root(self) -> "RailManifest":
        ontology_root = PurePosixPath(self.paths.ontology_root)
        for value in (
            self.hydration.ontology_file,
            self.hydration.sources_dir,
            self.hydration.pipelines_dir,
            self.hydration.transforms_dir,
        ):
            if value is None:
                continue
            if ontology_root not in PurePosixPath(value).parents and PurePosixPath(value) != ontology_root:
                raise ValueError("hydration paths must resolve inside ontology_root in V1")
        return self

    @model_validator(mode="after")
    def _apply_legacy_approval_shorthand(self) -> "RailManifest":
        legacy = self.agents.approval_required_for_write_runs
        if legacy is None:
            return self
        if legacy is False:
            raise ValueError(
                "approval_required_for_write_runs=false is not supported; use autonomy.mode explicitly"
            )
        if self.autonomy.mode != "assisted":
            raise ValueError(
                "approval_required_for_write_runs=true is only compatible with autonomy.mode=assisted"
            )
        return self

    @model_validator(mode="after")
    def _validate_phase_model(self) -> "RailManifest":
        if self.project.mode == "ontology_first":
            required = {"hydrated", "ontology_healthy"}
            if not required.issubset(set(self.lifecycle.phases)):
                raise ValueError("ontology_first projects must include hydrated and ontology_healthy lifecycle phases")
        return self

    def resolve_repo_path(self, project_root: str | Path, relative_path: str) -> Path:
        return Path(project_root).resolve() / relative_path


@dataclass(frozen=True)
class ContractViolation:
    path: str
    reason: str


class ManifestValidationError(ValueError):
    """Raised when rail.yaml parsing or repo-contract validation fails at project boot."""

    def __init__(
        self,
        message: str,
        *,
        violations: list[ContractViolation] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.violations = violations or []
        self.__cause__ = cause


def format_contract_violations(violations: list[ContractViolation]) -> str:
    if not violations:
        return ""
    return "\n".join(f"- {item.path}: {item.reason}" for item in violations)


def format_pydantic_validation_error(exc: ValidationError) -> str:
    lines: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        message = error.get("msg", "invalid value")
        if location:
            lines.append(f"{location}: {message}")
        else:
            lines.append(message)
    return "\n".join(lines)


def validate_repo_contract(manifest: RailManifest, project_root: str | Path) -> list[ContractViolation]:
    """Check that every required_path in the manifest exists on disk."""
    root = Path(project_root).resolve()
    violations: list[ContractViolation] = []
    for rel_path in manifest.repo_contract.required_paths:
        if not (root / rel_path).exists():
            violations.append(ContractViolation(path=rel_path, reason="required path does not exist"))
    return violations


def validate_manifest_semantics(manifest: RailManifest, project_root: str | Path) -> list[ContractViolation]:
    """Apply manifest-level rules beyond Pydantic field validation."""
    violations = list(validate_repo_contract(manifest, project_root))
    if not manifest.planner.task_root.strip():
        violations.append(ContractViolation(path="planner.task_root", reason="task_root is required"))
    if not manifest.planner.approval_root.strip():
        violations.append(ContractViolation(path="planner.approval_root", reason="approval_root is required"))
    return violations


def load_and_validate_manifest(project_root: str | Path) -> tuple[RailManifest, list[ContractViolation]]:
    """Load manifest and validate the repo structure against its contract."""
    manifest = load_manifest(project_root)
    violations = validate_manifest_semantics(manifest, project_root)
    return manifest, violations


def boot_validate_project(project_root: str | Path) -> RailManifest:
    """Load rail.yaml and enforce repo-contract validation. Raises ManifestValidationError on failure."""
    try:
        manifest, violations = load_and_validate_manifest(project_root)
    except FileNotFoundError as exc:
        raise ManifestValidationError(str(exc), cause=exc) from exc
    except ValueError as exc:
        raise ManifestValidationError(str(exc), cause=exc) from exc
    if violations:
        detail = format_contract_violations(violations)
        raise ManifestValidationError(
            "Project failed rail.yaml / repo-contract validation:\n" + detail,
            violations=violations,
        )
    return manifest


def parse_manifest_content(content: str) -> RailManifest:
    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("rail.yaml must parse to a mapping/object")
    try:
        return RailManifest.model_validate(raw)
    except ValidationError as exc:
        detail = format_pydantic_validation_error(exc)
        raise ValueError("Invalid rail.yaml:\n" + detail) from exc


def load_manifest(project_root: str | Path) -> RailManifest:
    manifest_path = Path(project_root).resolve() / "rail.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"rail.yaml not found in {manifest_path.parent}")
    return parse_manifest_content(manifest_path.read_text(encoding="utf-8"))
