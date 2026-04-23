from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


HydrationMode = Literal["full", "incremental"]
RunnerName = Literal["jules", "claude_code", "gemini_cli", "cursor_cli", "codex_cli"]
PlannerThreadMode = Literal["project"]
IndexMode = Literal["filesystem"]
HomeView = Literal["planner", "project_home", "artifacts"]


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


class AgentsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roles_dir: str = "agents"
    default_runner: RunnerName = "jules"
    sequential_execution: bool = True
    approval_required_for_write_runs: bool = True
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
        if not self.approval_required_for_write_runs:
            raise ValueError("V1 requires approval_required_for_write_runs=true")
        return self


class FrontendSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_index_mode: IndexMode = "filesystem"
    artifact_index_mode: IndexMode = "filesystem"
    show_repo_tree: bool = True
    show_task_board_snapshot: bool = True
    default_home_view: HomeView = "project_home"


class RailManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(..., ge=1)
    project: ProjectSection
    paths: PathsSection
    hydration: HydrationSection
    agents: AgentsSection
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

    def resolve_repo_path(self, project_root: str | Path, relative_path: str) -> Path:
        return Path(project_root).resolve() / relative_path


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
        raise ValueError(f"Invalid rail.yaml: {exc}") from exc


def load_manifest(project_root: str | Path) -> RailManifest:
    manifest_path = Path(project_root).resolve() / "rail.yaml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"rail.yaml not found in {manifest_path.parent}")
    return parse_manifest_content(manifest_path.read_text(encoding="utf-8"))
