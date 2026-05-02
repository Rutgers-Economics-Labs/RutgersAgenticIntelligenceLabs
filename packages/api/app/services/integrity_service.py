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

REPAIR_ACTIONS = {
    "plan_decomposition",
    "source_discovery",
    "data_ingestion",
    "analysis_scripts",
    "verification",
    "assumption_recording",
}
PROMOTION_ACTIONS = {"artifact_generation", "publish_changes"}


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


def evaluate_integrity_gate(
    project_root: str | Path,
    manifest: Any,
    *,
    action: str,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    indexes = load_integrity_indexes(project_root, plan_root=plan_root)
    integrity = manifest.integrity
    if action in REPAIR_ACTIONS:
        return {
            "blocked": False,
            "reasons": [],
            "indexes": indexes,
            "action": action,
            "blockingArtifacts": [],
            "blockingClaims": [],
            "blockingVerificationRuns": [],
        }

    reasons: list[str] = []
    blocking_artifacts: list[str] = []
    blocking_claims: list[str] = []
    blocking_verification_runs: list[str] = []

    stale_outputs = [
        row for row in indexes.artifact_lineage if row.promotion_state == "stale" or row.stale_reasons
    ]
    if action in PROMOTION_ACTIONS and integrity.stale_outputs_block_promotion and stale_outputs:
        blocking_artifacts.extend(row.artifact_path for row in stale_outputs)
        reasons.append("Stale outputs must be rerun and revalidated before promotion.")

    verification_failures = [run for run in indexes.verification_runs if run.status in {"failed", "blocked"}]
    if action in PROMOTION_ACTIONS and verification_failures:
        blocking_verification_runs.extend(run.run_id for run in verification_failures)
        reasons.append("Failed or blocked verification runs must be resolved before promotion.")

    if action in PROMOTION_ACTIONS and integrity.require_evidence_for_report_claims:
        unsupported_claims = [
            row for row in indexes.claims if row.status in {"draft", "unsupported", "needs_evidence"}
        ]
        if unsupported_claims:
            blocking_claims.extend(row.claim_key for row in unsupported_claims)
            reasons.append("Report claims need evidence before final artifacts can be promoted.")

    if action in PROMOTION_ACTIONS and integrity.require_source_for_datasets:
        unsourced_datasets = [
            row for row in indexes.artifact_lineage if row.artifact_type == "dataset" and not row.sources
        ]
        if unsourced_datasets:
            blocking_artifacts.extend(row.artifact_path for row in unsourced_datasets)
            reasons.append("Datasets must record source provenance before promotion.")

    if action in PROMOTION_ACTIONS and integrity.require_lineage_for_final_artifacts:
        lineage_gaps = [
            row
            for row in indexes.artifact_lineage
            if row.artifact_type != "dataset"
            and not (row.inputs or row.sources or row.assumptions or row.claims or row.scripts)
        ]
        if lineage_gaps:
            blocking_artifacts.extend(row.artifact_path for row in lineage_gaps)
            reasons.append("Final artifacts must record lineage before promotion.")

    return {
        "blocked": bool(reasons),
        "reasons": reasons,
        "indexes": indexes,
        "action": action,
        "blockingArtifacts": sorted(set(blocking_artifacts)),
        "blockingClaims": sorted(set(blocking_claims)),
        "blockingVerificationRuns": sorted(set(blocking_verification_runs)),
    }


def build_rerun_plan(
    project_root: str | Path,
    assumption_key: str,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    return build_batch_rerun_plan(project_root, [assumption_key], plan_root=plan_root)


def build_batch_rerun_plan(
    project_root: str | Path,
    assumption_keys: list[str],
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    all_assumptions = {item.assumption_key: item for item in repo.load_assumptions()}

    target_assumptions = []
    for key in assumption_keys:
        if key in all_assumptions:
            target_assumptions.append(all_assumptions[key])
        else:
            continue

    if not target_assumptions:
        return {
            "assumptions": [],
            "affectedArtifacts": [],
            "affectedPaths": [],
            "stalePaths": [],
            "proposedTasks": [],
        }

    # Consolidate impacts
    all_affected_artifacts: dict[str, ArtifactLineageRecord] = {}
    for a in target_assumptions:
        for item in repo.artifacts_for_assumption(a.assumption_key):
            all_affected_artifacts[item.artifact_path] = item

    affected_artifacts = list(all_affected_artifacts.values())
    affected_paths = sorted(all_affected_artifacts.keys())
    stale_paths = sorted([
        path for path, item in all_affected_artifacts.items()
        if item.promotion_state == "stale" or item.stale_reasons
    ])

    has_dataset = any(item.artifact_type == "dataset" for item in affected_artifacts)
    has_deliverables = any(item.artifact_type != "dataset" for item in affected_artifacts)

    # Build consolidated titles
    if len(target_assumptions) == 1:
        scope_desc = f"assumption {target_assumptions[0].title}"
    else:
        scope_desc = f"{len(target_assumptions)} changed assumptions"

    proposed_tasks: list[dict[str, Any]] = [
        {
            "title": f"Re-check evidence for {scope_desc}",
            "description": (
                f"Review the evidence and open questions affected by: "
                + ", ".join(f"`{a.assumption_key}`" for a in target_assumptions)
            ),
            "agentRole": "research",
            "repoPaths": ["topics", "research_plan"],
            "acceptanceCriteria": [
                "Affected claims are re-reviewed and gaps are documented.",
                "Updated source notes are recorded under topics/ or research_plan/.",
            ],
        }
    ]

    if has_dataset:
        proposed_tasks.append(
            {
                "title": f"Refresh datasets impacted by {scope_desc}",
                "description": "Regenerate or validate datasets whose lineage depends on the changed assumptions.",
                "agentRole": "data",
                "repoPaths": [".ontology", "topics", "research_plan"],
                "acceptanceCriteria": [
                    "Impacted datasets are regenerated or explicitly validated.",
                    "Source provenance remains recorded for each impacted dataset.",
                ],
            }
        )

    if has_deliverables:
        proposed_tasks.append(
            {
                "title": f"Regenerate affected outputs for {scope_desc}",
                "description": "Update analysis outputs and artifacts impacted by the changed assumptions.",
                "agentRole": "coding",
                "repoPaths": ["topics", "artifacts", "research_plan"],
                "acceptanceCriteria": [
                    "Affected outputs are regenerated.",
                    "Artifact lineage remains linked to assumptions, sources, and claims.",
                ],
            }
        )

    proposed_tasks.append(
        {
            "title": f"Re-verify outputs affected by {scope_desc}",
            "description": "Run deterministic verification and clear stale markers for rerun outputs that pass.",
            "agentRole": "health",
            "repoPaths": ["research_plan", "artifacts", "topics"],
            "acceptanceCriteria": [
                "Verification passes or blockers are recorded explicitly.",
                "Stale outputs are cleared only after successful revalidation.",
            ],
        }
    )

    return {
        "assumptions": [a.model_dump(mode="json") for a in target_assumptions],
        "affectedArtifacts": [item.model_dump(mode="json") for item in affected_artifacts],
        "affectedPaths": affected_paths,
        "stalePaths": stale_paths,
        "proposedTasks": proposed_tasks,
    }


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
    "evaluate_integrity_gate",
    "build_rerun_plan",
    "build_batch_rerun_plan",
]
