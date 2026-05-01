from __future__ import annotations

from pathlib import Path
from typing import Any

from rail.integrity import (
    ArtifactLineageRecord,
    AssumptionRecord,
    ClaimRecord,
    IntegrityIndexes,
    ResearchIntegrityRepo,
    SourceRecord,
    VerificationRunRecord,
)


def get_integrity_repo(project_root: str | Path, plan_root: str = "research_plan") -> ResearchIntegrityRepo:
    repo = ResearchIntegrityRepo(project_root, plan_root=plan_root)
    repo.ensure_files_exist()
    return repo


def load_integrity_indexes(project_root: str | Path, plan_root: str = "research_plan") -> IntegrityIndexes:
    return get_integrity_repo(project_root, plan_root=plan_root).load_all()


def rebuild_integrity_indexes(project_root: str | Path, plan_root: str = "research_plan") -> IntegrityIndexes:
    return get_integrity_repo(project_root, plan_root=plan_root).rebuild_all()


def update_assumption_and_mark_stale(
    project_root: str | Path,
    assumption_key: str,
    changes: dict[str, Any],
    *,
    plan_root: str = "research_plan",
) -> tuple[AssumptionRecord, list[ArtifactLineageRecord]]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    updated = repo.update_assumption(assumption_key, **changes)
    stale = repo.load_artifact_lineage()
    affected = [item for item in stale if item.promotion_state == "stale" and any(reason == f"assumption_changed:{assumption_key}" for reason in item.stale_reasons)]
    return updated, affected


__all__ = [
    "ArtifactLineageRecord",
    "AssumptionRecord",
    "ClaimRecord",
    "IntegrityIndexes",
    "SourceRecord",
    "VerificationRunRecord",
    "get_integrity_repo",
    "load_integrity_indexes",
    "rebuild_integrity_indexes",
    "update_assumption_and_mark_stale",
]
