from __future__ import annotations

import difflib
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.integrity_benchmarks import seed_default_integrity_benchmark_corpus
from rail.manifest import load_manifest
from rail.integrity import (
    ArtifactLineageRecord,
    AssumptionRecord,
    ClaimRecord,
    IntegrityIndexes,
    ResearchIntegrityRepo,
    SourceRecord,
    VerificationRunRecord,
    _normalize_reference_key,
    build_artifact_trust_summary,
    build_claim_state,
    build_source_state,
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
ALLOWED_PROMOTION_TRANSITIONS = {
    "exploratory": {"draft", "partially_verified"},
    "draft": {"partially_verified", "verified"},
    "needs_evidence": {"partially_verified"},
    "partially_verified": {"verified"},
    "verified": set(),
    "stale": {"partially_verified"},
    "blocked": {"partially_verified"},
}
DEFAULT_FRESHNESS_POLICY_DAYS: dict[str, tuple[int, int]] = {
    "dataset": (30, 60),
    "api": (30, 60),
    "document": (90, 180),
    "url": (14, 30),
    "text": (365, 730),
}
INTERNAL_DATASET_WORKFLOW_EXCLUSIONS = {
    ".ontology/.rail_hydration.json",
}


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _utc_datetime_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _duckdb_has_populated_rows(duckdb_path: str | Path | None) -> bool:
    if not duckdb_path:
        return False
    try:
        import duckdb  # type: ignore
    except Exception:
        return False
    try:
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchall()
        if not tables:
            conn.close()
            return False
        for (table_name,) in tables:
            try:
                count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            except Exception:
                continue
            if isinstance(count, int) and count > 0:
                conn.close()
                return True
        conn.close()
    except Exception:
        return False
    return False


def _artifact_order_key(artifact: ArtifactLineageRecord) -> tuple[int, str]:
    return (0 if artifact.artifact_type == "dataset" else 1, artifact.artifact_path)


def _order_artifacts_by_dependencies(artifacts: list[ArtifactLineageRecord]) -> list[ArtifactLineageRecord]:
    artifact_index = {item.artifact_path: item for item in artifacts}
    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = {item.artifact_path: set() for item in artifacts}
    indegree: dict[str, int] = {item.artifact_path: 0 for item in artifacts}

    for artifact in artifacts:
        direct_dependencies = {
            str(reference)
            for reference in artifact.inputs
            if str(reference) in artifact_index and str(reference) != artifact.artifact_path
        }
        dependencies[artifact.artifact_path] = direct_dependencies
        indegree[artifact.artifact_path] = len(direct_dependencies)
        for dependency_path in direct_dependencies:
            dependents.setdefault(dependency_path, set()).add(artifact.artifact_path)

    ready = sorted(
        [artifact_index[path] for path, degree in indegree.items() if degree == 0],
        key=_artifact_order_key,
    )
    ordered: list[ArtifactLineageRecord] = []

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        unlocked: list[ArtifactLineageRecord] = []
        for dependent_path in sorted(dependents.get(current.artifact_path, set())):
            indegree[dependent_path] -= 1
            if indegree[dependent_path] == 0:
                unlocked.append(artifact_index[dependent_path])
        if unlocked:
            ready = sorted(ready + unlocked, key=_artifact_order_key)

    if len(ordered) == len(artifacts):
        return ordered

    remaining_paths = [
        path
        for path in artifact_index
        if path not in {item.artifact_path for item in ordered}
    ]
    ordered.extend(sorted((artifact_index[path] for path in remaining_paths), key=_artifact_order_key))
    return ordered


def get_integrity_repo(project_root: str | Path, plan_root: str = "research_plan") -> ResearchIntegrityRepo:
    repo = ResearchIntegrityRepo(project_root, plan_root=plan_root)
    repo.ensure_files_exist()
    return repo


def load_integrity_indexes(project_root: str | Path, plan_root: str = "research_plan") -> IntegrityIndexes:
    return get_integrity_repo(project_root, plan_root=plan_root).load_all()


def rebuild_integrity_indexes(project_root: str | Path, plan_root: str = "research_plan") -> IntegrityIndexes:
    return get_integrity_repo(project_root, plan_root=plan_root).rebuild_all()


def audit_source_admissibility(
    project_root: str | Path,
    manifest: Any,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    """Audit all sources against the manifest integrity policy.

    Returns a dict with:
      admissibleCount (int), inadmissibleCount (int),
      inadmissibleSources (list of {sourceKey, admissibilityStatus, reason}),
      blockers (list[str])
    """
    indexes = load_integrity_indexes(project_root, plan_root=plan_root)
    allow_synthetic = bool(getattr(getattr(manifest, "integrity", None), "allow_synthetic_data", False))

    inadmissible: list[dict[str, Any]] = []
    admissible_count = 0

    for source in indexes.sources:
        state = _source_admissibility_state(source)
        if state in {"estimated", "missing"}:
            inadmissible.append({
                "sourceKey": source.source_key,
                "admissibilityStatus": state,
                "reason": f"Source has admissibility status '{state}' which is not allowed.",
            })
        elif state == "synthetic" and not allow_synthetic:
            inadmissible.append({
                "sourceKey": source.source_key,
                "admissibilityStatus": state,
                "reason": "Synthetic sources are not permitted by this project's integrity policy.",
            })
        else:
            admissible_count += 1

    blockers: list[str] = []
    if inadmissible:
        sample = ", ".join(item["sourceKey"] for item in inadmissible[:3])
        blockers.append(
            f"{len(inadmissible)} inadmissible source(s) detected: {sample}."
        )

    return {
        "admissibleCount": admissible_count,
        "inadmissibleCount": len(inadmissible),
        "inadmissibleSources": inadmissible,
        "blockers": blockers,
    }


def audit_artifact_lineage(
    project_root: str | Path,
    manifest: Any,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    """Audit artifact lineage completeness against the manifest integrity policy.

    Returns a dict with:
      compliantCount (int),
      nonCompliantArtifacts (list of {path, missingLineage, missingVerification}),
      blockers (list[str])
    """
    require_lineage = bool(
        getattr(getattr(manifest, "integrity", None), "require_lineage_for_final_artifacts", True)
    )
    if not require_lineage:
        return {"compliantCount": 0, "nonCompliantArtifacts": [], "blockers": []}

    indexes = load_integrity_indexes(project_root, plan_root=plan_root)
    artifacts_root = str(getattr(getattr(manifest, "paths", None), "artifacts_root", "artifacts"))

    non_compliant: list[dict[str, Any]] = []
    compliant_count = 0

    for row in indexes.artifact_lineage:
        path = str(row.artifact_path)
        if row.artifact_type == "dataset":
            continue
        if not (path == artifacts_root or path.startswith(f"{artifacts_root}/")):
            continue
        if row.reproducibility_mode in {"manual", "non_reproducible"}:
            compliant_count += 1
            continue

        missing_lineage = not (row.inputs and row.scripts)
        missing_verification = not row.verification_runs
        if missing_lineage or missing_verification:
            non_compliant.append({
                "path": path,
                "missingLineage": missing_lineage,
                "missingVerification": missing_verification,
            })
        else:
            compliant_count += 1

    blockers: list[str] = []
    if non_compliant:
        sample = ", ".join(item["path"] for item in non_compliant[:3])
        blockers.append(
            f"{len(non_compliant)} final artifact(s) missing lineage or verification: {sample}."
        )

    return {
        "compliantCount": compliant_count,
        "nonCompliantArtifacts": non_compliant,
        "blockers": blockers,
    }


def register_final_artifact(
    project_root: str | Path,
    *,
    artifact_path: str,
    artifact_type: str,
    title: str,
    inputs: list[str] | None = None,
    scripts: list[str] | None = None,
    sources: list[str] | None = None,
    claims: list[str] | None = None,
    verification_commands: list[str] | None = None,
    reproducibility_mode: str | None = None,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    """Register or update a final artifact with full lineage in the integrity index.

    Returns the upserted artifact record as a dict.
    """
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    record = ArtifactLineageRecord(
        artifact_path=artifact_path,
        artifact_type=artifact_type,
        title=title,
        inputs=inputs or [],
        scripts=scripts or [],
        sources=sources or [],
        claims=claims or [],
        verification_commands=verification_commands or [],
        reproducibility_mode=reproducibility_mode,
    )
    upserted = repo.upsert_artifact_lineage(record)
    return upserted.model_dump(mode="json")


def write_verification_certificate(
    project_root: str | Path,
    artifact_path: str,
    *,
    run_id: str,
    session_id: str | None = None,
    verified_at: str | None = None,
    notes: str | None = None,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    """Write a human-readable verification certificate for a verified artifact.

    The certificate is written to research_plan/verification_certificates/<run_id>.md
    and can be committed as part of the project's audit trail.
    Returns a dict with certificatePath and content.
    """
    now = verified_at or _utc_datetime_now().isoformat().replace("+00:00", "Z")
    cert_dir = Path(project_root) / plan_root / "verification_certificates"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / f"{run_id}.md"

    lines = [
        "# Verification Certificate",
        "",
        f"**Artifact:** `{artifact_path}`",
        f"**Run ID:** `{run_id}`",
        f"**Verified At:** {now}",
    ]
    if session_id:
        lines.append(f"**Session:** `{session_id}`")
    if notes:
        lines.extend(["", "## Notes", "", notes])
    lines.append("")
    content = "\n".join(lines)
    cert_path.write_text(content, encoding="utf-8")
    return {"certificatePath": str(cert_path), "content": content}


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


def update_source_and_mark_stale(
    project_root: str | Path,
    source_key: str,
    changes: dict[str, Any],
    *,
    plan_root: str = "research_plan",
) -> tuple[SourceRecord, list[ClaimRecord], list[ArtifactLineageRecord]]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    return repo.update_source(source_key, **changes)


def mark_script_change_and_list_stale(
    project_root: str | Path,
    script_path: str,
    *,
    plan_root: str = "research_plan",
) -> list[ArtifactLineageRecord]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    return repo.mark_artifacts_stale_for_script(script_path)


def apply_source_freshness_policy(
    project_root: str | Path,
    *,
    as_of: str | None = None,
    policy_days: dict[str, tuple[int, int]] | None = None,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    policy = {**DEFAULT_FRESHNESS_POLICY_DAYS, **(policy_days or {})}
    now = _parse_timestamp(as_of) or _utc_datetime_now()

    changed_sources: list[dict[str, Any]] = []
    affected_claims: dict[str, dict[str, Any]] = {}
    affected_artifacts: dict[str, dict[str, Any]] = {}
    summary = {"fresh": 0, "needs_refresh": 0, "stale": 0, "unknown": 0}

    for source in repo.load_sources():
        recorded_at = _parse_timestamp(source.acquired_at) or _parse_timestamp(source.retrieved_at)
        if recorded_at is None:
            summary["unknown"] += 1
            continue
        refresh_days, stale_days = policy.get(source.source_type, (30, 60))
        age_days = max(0, int((now - recorded_at).total_seconds() // 86400))
        if age_days >= stale_days:
            next_status = "stale"
        elif age_days >= refresh_days:
            next_status = "needs_refresh"
        else:
            next_status = "fresh"
        summary[next_status] += 1
        if next_status == source.freshness_status:
            continue
        updated, claims, artifacts = repo.update_source(source.source_key, freshness_status=next_status)
        changed_sources.append(
            {
                "source": updated.model_dump(mode="json"),
                "previousStatus": source.freshness_status,
                "nextStatus": next_status,
                "ageDays": age_days,
            }
        )
        for claim in claims:
            affected_claims[claim.claim_key] = claim.model_dump(mode="json")
        for artifact in artifacts:
            affected_artifacts[artifact.artifact_path] = artifact.model_dump(mode="json")

    return {
        "evaluatedAt": now.isoformat().replace("+00:00", "Z"),
        "changedSources": changed_sources,
        "affectedClaims": list(affected_claims.values()),
        "affectedArtifacts": list(affected_artifacts.values()),
        "summary": summary,
    }


def _source_has_provenance(source: SourceRecord | None) -> bool:
    if source is None:
        return False
    has_origin = bool(source.origin or source.url_or_path)
    has_acquired_at = bool(source.acquired_at or source.retrieved_at)
    has_access_method = bool(source.access_method or source.source_type)
    return has_origin and has_acquired_at and has_access_method


def _source_has_freshness(source: SourceRecord | None) -> bool:
    if source is None:
        return False
    return bool(source.freshness_status and source.freshness_status != "unknown")


def _source_admissibility_state(source: SourceRecord | None) -> str | None:
    if source is None:
        return None
    state = build_source_state(source)
    return str(state.get("admissibilityStatus") or "")


def summarize_agent_workflow_health(
    project_root: str | Path,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    indexes = load_integrity_indexes(project_root, plan_root=plan_root)
    source_by_key = {str(item.source_key): item for item in indexes.sources}

    def _claim_needs_evidence(claim: ClaimRecord) -> bool:
        has_evidence = bool(claim.evidence_paths or claim.source_keys or claim.evidence_chunk_keys)
        return (
            claim.status in {"draft", "unsupported", "needs_evidence", "stale", "conflicted"}
            or (claim.status == "supported" and not has_evidence)
            or (claim.status == "supported" and claim.evidence_kind == "semantic_suggestion")
        )

    datasets_missing_provenance = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type == "dataset"
        and row.artifact_path not in INTERNAL_DATASET_WORKFLOW_EXCLUSIONS
        and (
            not row.sources
            or any(not _source_has_provenance(source_by_key.get(_normalize_reference_key(reference))) for reference in row.sources)
        )
    ]
    datasets_missing_freshness = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type == "dataset"
        and row.artifact_path not in INTERNAL_DATASET_WORKFLOW_EXCLUSIONS
        and (
            not row.sources
            or any(not _source_has_freshness(source_by_key.get(_normalize_reference_key(reference))) for reference in row.sources)
        )
    ]
    analysis_missing_lineage = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type != "dataset"
        and row.reproducibility_mode not in {"manual", "non_reproducible"}
        and not (row.inputs and row.scripts)
    ]
    analysis_missing_verification_commands = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type != "dataset"
        and row.reproducibility_mode not in {"manual", "non_reproducible"}
        and not row.verification_commands
    ]
    analysis_missing_verification = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type != "dataset"
        and not row.verification_runs
        and row.reproducibility_mode not in {"manual", "non_reproducible"}
    ]
    unsupported_claim_keys = {row.claim_key for row in indexes.claims if _claim_needs_evidence(row)}
    artifacts_with_unsupported_claims = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if {_normalize_reference_key(reference) for reference in row.claims}.intersection(unsupported_claim_keys)
    ]
    stale_source_keys = [
        row.source_key
        for row in indexes.sources
        if row.freshness_status in {"needs_refresh", "stale"}
    ]
    inadmissible_source_keys = [
        row.source_key
        for row in indexes.sources
        if _source_admissibility_state(row) in {"estimated", "synthetic", "missing"}
    ]
    reproducibility_gaps = [
        row.artifact_path
        for row in indexes.artifact_lineage
        if row.artifact_type != "dataset"
        and row.reproducibility_mode is None
        and not (row.inputs and row.scripts)
    ]
    missing_evidence_claims = sorted(unsupported_claim_keys)
    verification_failures = [
        row.run_id
        for row in indexes.verification_runs
        if row.status in {"failed", "blocked"}
    ]

    def _status(blockers: list[str]) -> str:
        return "blocked" if blockers else "ready"

    return {
        "research": {
            "status": "ready",
            "requirements": [
                "Separate facts, interpretations, and open questions in research outputs.",
                "Record caveats for non-final empirical claims.",
            ],
        },
        "data": {
            "status": _status(sorted(set(datasets_missing_provenance + datasets_missing_freshness))),
            "datasetsMissingProvenance": datasets_missing_provenance,
            "datasetsMissingFreshness": datasets_missing_freshness,
            "requirements": [
                "Datasets must retain source provenance and freshness metadata.",
            ],
        },
        "coding": {
            "status": _status(
                sorted(
                    set(
                        analysis_missing_lineage
                        + analysis_missing_verification_commands
                        + analysis_missing_verification
                    )
                )
            ),
            "artifactsMissingLineage": analysis_missing_lineage,
            "artifactsMissingVerificationCommands": analysis_missing_verification_commands,
            "artifactsMissingVerification": analysis_missing_verification,
            "requirements": [
                "Analysis outputs must declare inputs and scripts.",
                "Deterministic analyses must declare verification commands before handoff.",
                "Deterministic analyses must carry verification runs before handoff.",
            ],
        },
        "artifact": {
            "status": _status(artifacts_with_unsupported_claims),
            "artifactsWithUnsupportedClaims": artifacts_with_unsupported_claims,
            "requirements": [
                "Artifact narratives must preserve evidence links.",
                "Artifacts with unsupported claims cannot be treated as trusted.",
            ],
        },
        "health": {
            "status": _status(
                sorted(
                    set(
                        missing_evidence_claims
                        + stale_source_keys
                        + inadmissible_source_keys
                        + reproducibility_gaps
                        + verification_failures
                    )
                )
            ),
            "missingEvidenceClaims": missing_evidence_claims,
            "staleSources": stale_source_keys,
            "inadmissibleSources": inadmissible_source_keys,
            "reproducibilityGaps": reproducibility_gaps,
            "failedVerificationRuns": verification_failures,
            "requirements": [
                "Detect missing evidence, stale sources, inadmissible sources, and reproducibility gaps.",
            ],
        },
    }


def evaluate_integrity_gate(
    project_root: str | Path,
    manifest: Any,
    *,
    action: str,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    indexes = load_integrity_indexes(project_root, plan_root=plan_root)
    integrity = manifest.integrity
    gate_actions = set(getattr(manifest.verification, "require_integrity_gate_for", []) or [])
    enforce_promotion_rules = action in PROMOTION_ACTIONS or action in gate_actions
    if action in REPAIR_ACTIONS:
        return {
            "blocked": False,
            "reasons": [],
            "indexes": indexes.model_dump(mode="json"),
            "action": action,
            "blockingArtifacts": [],
            "blockingClaims": [],
            "blockingVerificationRuns": [],
        }

    reasons: list[str] = []
    blocking_artifacts: list[str] = []
    blocking_claims: list[str] = []
    blocking_verification_runs: list[str] = []
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    source_index = {row.source_key: row for row in indexes.sources}

    stale_outputs = [
        row for row in indexes.artifact_lineage if row.promotion_state == "stale" or row.stale_reasons
    ]
    stale_source_artifacts = [
        artifact.artifact_path
        for source_key, source in source_index.items()
        if source.freshness_status == "stale"
        for artifact in repo.artifacts_for_source(source_key)
    ]
    blocked_source_artifacts = [
        artifact.artifact_path
        for source_key, source in source_index.items()
        if source.quality_status in {"blocked", "rejected"}
        for artifact in repo.artifacts_for_source(source_key)
    ]
    inadmissible_source_artifacts = [
        artifact.artifact_path
        for source_key, source in source_index.items()
        if _source_admissibility_state(source) in {"estimated", "synthetic", "missing"}
        for artifact in repo.artifacts_for_source(source_key)
    ]
    if enforce_promotion_rules and integrity.stale_outputs_block_promotion and stale_outputs:
        blocking_artifacts.extend(row.artifact_path for row in stale_outputs)
        reasons.append("Stale outputs must be rerun and revalidated before promotion.")
    if enforce_promotion_rules and stale_source_artifacts:
        blocking_artifacts.extend(stale_source_artifacts)
        reasons.append("Artifacts that depend on stale sources must be rerun before promotion.")
    if enforce_promotion_rules and blocked_source_artifacts:
        blocking_artifacts.extend(blocked_source_artifacts)
        reasons.append("Artifacts that depend on blocked or rejected sources cannot be promoted.")
    if enforce_promotion_rules and inadmissible_source_artifacts:
        blocking_artifacts.extend(inadmissible_source_artifacts)
        reasons.append("Artifacts that depend on estimated, synthetic, or missing sources cannot be promoted as trusted outputs.")

    verification_failures = [run for run in indexes.verification_runs if run.status in {"failed", "blocked"}]
    if enforce_promotion_rules and verification_failures:
        blocking_verification_runs.extend(run.run_id for run in verification_failures)
        reasons.append("Failed or blocked verification runs must be resolved before promotion.")

    conflicted_claims = [row for row in indexes.claims if row.status == "conflicted"]
    conflicted_claim_artifacts = [
        artifact.artifact_path
        for artifact in indexes.artifact_lineage
        if {
            _normalize_reference_key(reference)
            for reference in artifact.claims
        }.intersection({row.claim_key for row in conflicted_claims})
    ]
    if enforce_promotion_rules and conflicted_claim_artifacts:
        blocking_artifacts.extend(conflicted_claim_artifacts)
        blocking_claims.extend(row.claim_key for row in conflicted_claims)
        reasons.append("Conflicted claims must be resolved before final artifacts can be promoted.")

    if enforce_promotion_rules and integrity.require_evidence_for_report_claims:
        unsupported_claims = [
            row
            for row in indexes.claims
            if row.status in {"draft", "unsupported", "needs_evidence", "stale", "conflicted"}
            or (row.status == "supported" and not (row.evidence_paths or row.source_keys or row.evidence_chunk_keys))
            or (row.status == "supported" and row.evidence_kind == "semantic_suggestion")
        ]
        if unsupported_claims:
            unsupported_claim_keys = {row.claim_key for row in unsupported_claims}
            unsupported_claim_artifacts = [
                artifact.artifact_path
                for artifact in indexes.artifact_lineage
                if {
                    _normalize_reference_key(reference)
                    for reference in artifact.claims
                }.intersection(unsupported_claim_keys)
            ]
            blocking_artifacts.extend(unsupported_claim_artifacts)
            blocking_claims.extend(row.claim_key for row in unsupported_claims)
            reasons.append("Report claims need evidence before final artifacts can be promoted.")

    if enforce_promotion_rules and integrity.require_source_for_datasets:
        unsourced_datasets = [
            row for row in indexes.artifact_lineage if row.artifact_type == "dataset" and not row.sources
        ]
        missing_provenance_datasets = [
            row.artifact_path
            for row in indexes.artifact_lineage
            if row.artifact_type == "dataset"
            and row.sources
            and any(not _source_has_provenance(source_index.get(_normalize_reference_key(reference))) for reference in row.sources)
        ]
        if unsourced_datasets:
            blocking_artifacts.extend(row.artifact_path for row in unsourced_datasets)
            reasons.append("Datasets must record source provenance before promotion.")
        if missing_provenance_datasets:
            blocking_artifacts.extend(missing_provenance_datasets)
            reasons.append("Referenced sources must record provenance before datasets can be promoted.")

    if enforce_promotion_rules and integrity.require_lineage_for_final_artifacts:
        lineage_gaps = [
            row
            for row in indexes.artifact_lineage
            if row.artifact_type != "dataset"
            and not (row.inputs or row.sources or row.assumptions or row.claims or row.scripts)
        ]
        final_artifact_provenance_gaps = [
            row.artifact_path
            for row in indexes.artifact_lineage
            if row.artifact_type != "dataset"
            and row.sources
            and any(not _source_has_provenance(source_index.get(_normalize_reference_key(reference))) for reference in row.sources)
        ]
        reproducibility_gaps = [
            row
            for row in indexes.artifact_lineage
            if row.artifact_type != "dataset"
            and row.reproducibility_mode not in {"manual", "non_reproducible"}
            and (
                not row.inputs
                or not row.scripts
                or not row.verification_commands
                or not row.verification_runs
            )
        ]
        unlabeled_manual_artifacts = [
            row.artifact_path
            for row in indexes.artifact_lineage
            if row.artifact_type != "dataset"
            and row.reproducibility_mode is None
            and not row.inputs
            and not row.scripts
            and not row.verification_commands
            and not row.verification_runs
        ]
        if lineage_gaps:
            blocking_artifacts.extend(row.artifact_path for row in lineage_gaps)
            reasons.append("Final artifacts must record lineage before promotion.")
        if final_artifact_provenance_gaps:
            blocking_artifacts.extend(final_artifact_provenance_gaps)
            reasons.append("Referenced sources must record provenance before final artifacts can be promoted.")
        if unlabeled_manual_artifacts:
            blocking_artifacts.extend(unlabeled_manual_artifacts)
            reasons.append("Manual or non-reproducible artifacts must be explicitly labeled.")
        if reproducibility_gaps:
            blocking_artifacts.extend(row.artifact_path for row in reproducibility_gaps)
            reasons.append(
                "Final artifacts need inputs, scripts, verification commands, and verification runs before promotion."
            )

    return {
        "blocked": bool(reasons),
        "reasons": reasons,
        "indexes": indexes.model_dump(mode="json"),
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
    plan = build_batch_rerun_plan(project_root, [assumption_key], plan_root=plan_root)
    assumptions = plan.get("assumptions") or []
    plan["assumption"] = assumptions[0] if assumptions else None
    return plan


def get_source_detail(
    project_root: str | Path,
    source_key: str,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    source = repo.get_source(source_key)
    if source is None:
        raise KeyError(f"Unknown source_key: {source_key}")
    dependent_claims = repo.claims_for_source(source_key)
    dependent_artifacts = repo.artifacts_for_source(source_key)
    chunks = repo.chunks_for_source(source_key)
    source_state = build_source_state(
        source,
        dependent_claim_count=len(dependent_claims),
        dependent_artifact_count=len(dependent_artifacts),
        chunk_count=len(chunks),
    )
    return {
        "source": source.model_dump(mode="json"),
        "dependentClaims": [item.model_dump(mode="json") for item in dependent_claims],
        "dependentArtifacts": [item.model_dump(mode="json") for item in dependent_artifacts],
        "chunks": [item.model_dump(mode="json") for item in chunks],
        "sourceState": source_state,
        "trustSummary": {
            "entityType": "source",
            "currentState": source.freshness_status,
            "isTrusted": source_state["isFresh"],
            "isBlocked": source_state["isBlocked"],
            "isStale": source_state["isStale"],
            "hasEvidence": bool(dependent_claims or dependent_artifacts),
            "hasFreshSources": source_state["isFresh"],
            "isReproducible": True,
            "blockingClaims": [],
            "blockingSources": [source.source_key] if source_state["isBlocked"] or source_state["isStale"] else [],
            "blockingArtifacts": [item.artifact_path for item in dependent_artifacts if item.promotion_state in {"blocked", "stale"}],
            "blockingVerificationRuns": [],
            "recommendedNextAction": (
                "Refresh this source and rerun dependent analyses."
                if source_state["needsRefresh"] or source_state["isStale"]
                else "Resolve source quality issues before using it for trusted outputs."
                if source_state["isBlocked"]
                else "Source state is current."
            ),
        },
    }


def list_source_summaries(
    project_root: str | Path,
    *,
    plan_root: str = "research_plan",
) -> list[dict[str, Any]]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    rows = []
    for source in repo.load_sources():
        dependent_claims = repo.claims_for_source(source.source_key)
        dependent_artifacts = repo.artifacts_for_source(source.source_key)
        chunks = repo.chunks_for_source(source.source_key)
        source_state = build_source_state(
            source,
            dependent_claim_count=len(dependent_claims),
            dependent_artifact_count=len(dependent_artifacts),
            chunk_count=len(chunks),
        )
        rows.append(
            {
                **source.model_dump(mode="json"),
                "sourceState": source_state,
                "trustSummary": {
                    "entityType": "source",
                    "currentState": source.freshness_status,
                    "isTrusted": source_state["isFresh"],
                    "isBlocked": source_state["isBlocked"],
                    "isStale": source_state["isStale"],
                    "hasEvidence": bool(dependent_claims or dependent_artifacts),
                    "hasFreshSources": source_state["isFresh"],
                    "isReproducible": True,
                    "blockingClaims": [],
                    "blockingSources": [source.source_key] if source_state["isBlocked"] or source_state["isStale"] else [],
                    "blockingArtifacts": [item.artifact_path for item in dependent_artifacts if item.promotion_state in {"blocked", "stale"}],
                    "blockingVerificationRuns": [],
                    "recommendedNextAction": (
                        "Refresh this source and rerun dependent analyses."
                        if source_state["needsRefresh"] or source_state["isStale"]
                        else "Resolve source quality issues before using it for trusted outputs."
                        if source_state["isBlocked"]
                        else "Source state is current."
                    ),
                },
            }
        )
    return rows


def get_claim_detail(
    project_root: str | Path,
    claim_key: str,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    claim = repo.get_claim(claim_key)
    if claim is None:
        raise KeyError(f"Unknown claim_key: {claim_key}")
    sources = [source.model_dump(mode="json") for source in repo.load_sources() if source.source_key in claim.source_keys]
    contradictory_claims = [
        item.model_dump(mode="json")
        for item in repo.load_claims()
        if item.claim_key in claim.contradicts_claim_keys
    ]
    chunks = [chunk.model_dump(mode="json") for chunk in repo.chunks_for_claim(claim_key)]
    artifacts = repo.artifacts_for_claim(claim_key)
    artifact_paths = [item.artifact_path for item in artifacts]
    verification_runs = repo.verification_runs_for_artifact_paths(artifact_paths)
    claim_state = build_claim_state(
        claim,
        contradictory_claim_count=len(contradictory_claims),
        source_count=len(sources),
        chunk_count=len(chunks),
        artifact_count=len(artifacts),
        verification_run_count=len(verification_runs),
    )
    return {
        "claim": claim.model_dump(mode="json"),
        "sources": sources,
        "contradictoryClaims": contradictory_claims,
        "chunks": chunks,
        "artifacts": [item.model_dump(mode="json") for item in artifacts],
        "verificationRuns": [item.model_dump(mode="json") for item in verification_runs],
        "claimState": claim_state,
        "trustSummary": {
            "entityType": "claim",
            "currentState": claim.status,
            "isTrusted": claim_state["isExplicitEvidence"],
            "isBlocked": claim.status == "conflicted",
            "isStale": claim.status == "stale",
            "hasEvidence": claim_state["evidenceComplete"],
            "hasFreshSources": all(item.get("freshness_status") == "fresh" for item in sources) if sources else False,
            "isReproducible": bool(verification_runs),
            "blockingClaims": [claim.claim_key] if claim.status in {"needs_evidence", "unsupported", "draft", "conflicted", "stale"} else [],
            "blockingSources": [item["source_key"] for item in sources if item.get("freshness_status") == "stale" or item.get("quality_status") in {"blocked", "rejected"}],
            "blockingArtifacts": [item.artifact_path for item in artifacts if item.promotion_state in {"blocked", "stale", "needs_evidence"}],
            "blockingVerificationRuns": [item.run_id for item in verification_runs if item.status in {"failed", "blocked"}],
            "recommendedNextAction": (
                "Attach explicit evidence before relying on this claim."
                if not claim_state["evidenceComplete"]
                else "Resolve contradictory claims before promotion."
                if claim.status == "conflicted"
                else "Refresh stale sources or rerun dependent analyses."
                if claim.status == "stale"
                else "Claim state is current."
            ),
        },
    }


def list_claim_summaries(
    project_root: str | Path,
    *,
    plan_root: str = "research_plan",
) -> list[dict[str, Any]]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    rows = []
    for claim in repo.load_claims():
        sources = [source for source in repo.load_sources() if source.source_key in claim.source_keys]
        chunks = repo.chunks_for_claim(claim.claim_key)
        artifacts = repo.artifacts_for_claim(claim.claim_key)
        artifact_paths = [item.artifact_path for item in artifacts]
        verification_runs = repo.verification_runs_for_artifact_paths(artifact_paths)
        contradictory_claims = [
            item
            for item in repo.load_claims()
            if item.claim_key in claim.contradicts_claim_keys
        ]
        claim_state = build_claim_state(
            claim,
            contradictory_claim_count=len(contradictory_claims),
            source_count=len(sources),
            chunk_count=len(chunks),
            artifact_count=len(artifacts),
            verification_run_count=len(verification_runs),
        )
        rows.append(
            {
                **claim.model_dump(mode="json"),
                "claimState": claim_state,
                "trustSummary": {
                    "entityType": "claim",
                    "currentState": claim.status,
                    "isTrusted": claim_state["isExplicitEvidence"],
                    "isBlocked": claim.status == "conflicted",
                    "isStale": claim.status == "stale",
                    "hasEvidence": claim_state["evidenceComplete"],
                    "hasFreshSources": all(source.freshness_status == "fresh" for source in sources) if sources else False,
                    "isReproducible": bool(verification_runs),
                    "blockingClaims": [claim.claim_key] if claim.status in {"needs_evidence", "unsupported", "draft", "conflicted", "stale"} else [],
                    "blockingSources": [source.source_key for source in sources if source.freshness_status == "stale" or source.quality_status in {"blocked", "rejected"}],
                    "blockingArtifacts": [item.artifact_path for item in artifacts if item.promotion_state in {"blocked", "stale", "needs_evidence"}],
                    "blockingVerificationRuns": [item.run_id for item in verification_runs if item.status in {"failed", "blocked"}],
                    "recommendedNextAction": (
                        "Attach explicit evidence before relying on this claim."
                        if not claim_state["evidenceComplete"]
                        else "Resolve contradictory claims before promotion."
                        if claim.status == "conflicted"
                        else "Refresh stale sources or rerun dependent analyses."
                        if claim.status == "stale"
                        else "Claim state is current."
                    ),
                },
            }
        )
    return rows


def get_artifact_detail(
    project_root: str | Path,
    artifact_path: str,
    *,
    manifest: Any | None = None,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    artifact = next((item for item in repo.load_artifact_lineage() if item.artifact_path == artifact_path), None)
    if artifact is None:
        raise KeyError(f"Unknown artifact_path: {artifact_path}")

    source_keys = sorted({_normalize_reference_key(reference) for reference in artifact.sources})
    claim_keys = sorted({_normalize_reference_key(reference) for reference in artifact.claims})
    assumption_keys = sorted({_normalize_reference_key(reference) for reference in artifact.assumptions})
    verification_run_ids = sorted({_normalize_reference_key(reference) for reference in artifact.verification_runs})

    sources = [item for item in repo.load_sources() if item.source_key in source_keys]
    claims = [item for item in repo.load_claims() if item.claim_key in claim_keys]
    assumptions = [item for item in repo.load_assumptions() if item.assumption_key in assumption_keys]
    verification_runs = [item for item in repo.load_verification_runs() if item.run_id in verification_run_ids]

    gate_manifest = manifest or load_manifest(project_root)
    gate = evaluate_integrity_gate(project_root, gate_manifest, action="artifact_generation", plan_root=plan_root)
    gate_blocking_artifacts = set(gate.get("blockingArtifacts") or [])
    gate_blocking_claims = set(gate.get("blockingClaims") or [])
    gate_blocking_runs = set(gate.get("blockingVerificationRuns") or [])
    gate_blocking_sources = {
        source.source_key
        for source in sources
        if source.freshness_status == "stale" or source.quality_status in {"blocked", "rejected"}
    }
    artifact_blocked = artifact.artifact_path in gate_blocking_artifacts or artifact.promotion_state == "blocked"
    eligible_transitions = sorted(ALLOWED_PROMOTION_TRANSITIONS.get(artifact.promotion_state, set()))
    promotable_targets = [] if artifact_blocked else eligible_transitions
    verification_status = "unverified"
    verification_statuses = [run.status for run in verification_runs]
    if artifact.promotion_state == "stale":
        verification_status = "stale"
    elif verification_statuses:
        if "failed" in verification_statuses:
            verification_status = "failed"
        elif "blocked" in verification_statuses:
            verification_status = "blocked"
        elif "pending" in verification_statuses:
            verification_status = "pending"
        elif all(status == "passed" for status in verification_statuses):
            verification_status = "passed"
    trust_state = build_artifact_trust_summary(
        artifact,
        verification_status=verification_status,
        artifact_blocked=artifact_blocked,
        gate_reasons=list(gate.get("reasons") or []),
        eligible_transitions=eligible_transitions,
        promotable_targets=promotable_targets,
        blocking_claims=[claim_key for claim_key in claim_keys if claim_key in gate_blocking_claims],
        blocking_sources=[source_key for source_key in source_keys if source_key in gate_blocking_sources],
        blocking_artifacts=[artifact.artifact_path] if artifact.artifact_path in gate_blocking_artifacts else [],
        blocking_verification_runs=[run_id for run_id in verification_run_ids if run_id in gate_blocking_runs],
    )

    return {
        "artifact": artifact.model_dump(mode="json"),
        "sources": [item.model_dump(mode="json") for item in sources],
        "claims": [item.model_dump(mode="json") for item in claims],
        "assumptions": [item.model_dump(mode="json") for item in assumptions],
        "verificationRuns": [item.model_dump(mode="json") for item in verification_runs],
        "trustState": trust_state,
        "trustSummary": trust_state,
        "summary": {
            "sourceCount": len(sources),
            "claimCount": len(claims),
            "assumptionCount": len(assumptions),
            "verificationRunCount": len(verification_runs),
            "staleReasonCount": len(artifact.stale_reasons),
        },
        "gate": gate,
    }


def get_integrity_dependency_graph(
    project_root: str | Path,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    indexes = repo.load_all()

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    method_paths = sorted({script for artifact in indexes.artifact_lineage for script in artifact.scripts})
    artifact_index = {row.artifact_path: row for row in indexes.artifact_lineage}

    def _artifact_node_id(row: ArtifactLineageRecord) -> str:
        prefix = "dataset" if row.artifact_type == "dataset" else "artifact"
        return f"{prefix}:{row.artifact_path}"

    for row in indexes.sources:
        nodes.append(
            {
                "id": f"source:{row.source_key}",
                "type": "source",
                "recordKey": row.source_key,
                "label": row.title,
                "status": row.freshness_status,
                "qualityStatus": row.quality_status,
            }
        )
    for row in indexes.evidence_chunks:
        nodes.append(
            {
                "id": f"chunk:{row.chunk_key}",
                "type": "chunk",
                "recordKey": row.chunk_key,
                "label": row.metadata.get("source_title") or row.chunk_key,
                "status": row.status,
                "sourceKey": row.source_key,
            }
        )
    for row in indexes.claims:
        nodes.append(
            {
                "id": f"claim:{row.claim_key}",
                "type": "claim",
                "recordKey": row.claim_key,
                "label": row.claim_text,
                "status": row.status,
                "evidenceKind": row.evidence_kind,
            }
        )
    for row in indexes.assumptions:
        nodes.append(
            {
                "id": f"assumption:{row.assumption_key}",
                "type": "assumption",
                "recordKey": row.assumption_key,
                "label": row.title,
                "status": row.status,
            }
        )
    for path in method_paths:
        nodes.append(
            {
                "id": f"method:{path}",
                "type": "method",
                "recordKey": path,
                "label": path,
                "status": "declared",
            }
        )
    for row in indexes.artifact_lineage:
        nodes.append(
            {
                "id": _artifact_node_id(row),
                "type": "dataset" if row.artifact_type == "dataset" else "artifact",
                "recordKey": row.artifact_path,
                "label": row.title,
                "status": row.promotion_state,
                "artifactType": row.artifact_type,
            }
        )
    for row in indexes.verification_runs:
        nodes.append(
            {
                "id": f"verification_run:{row.run_id}",
                "type": "verification_run",
                "recordKey": row.run_id,
                "label": row.run_id,
                "status": row.status,
                "loopType": row.loop_type,
            }
        )
    edges = [
        {
            "from": edge.from_id,
            "to": edge.to_id,
            "relationship": edge.relationship,
            "edgeClass": edge.edge_class,
            "edgeKey": edge.edge_key,
            "sourceRecordKey": edge.source_record_key,
            "targetRecordKey": edge.target_record_key,
            "metadata": dict(edge.metadata),
        }
        for edge in repo.load_integrity_edges()
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "sourceCount": len(indexes.sources),
            "chunkCount": len(indexes.evidence_chunks),
            "claimCount": len(indexes.claims),
            "assumptionCount": len(indexes.assumptions),
            "methodCount": len(method_paths),
            "datasetCount": sum(1 for row in indexes.artifact_lineage if row.artifact_type == "dataset"),
            "artifactCount": sum(1 for row in indexes.artifact_lineage if row.artifact_type != "dataset"),
            "verificationRunCount": len(indexes.verification_runs),
        },
    }


def get_stale_dependency_graph(
    project_root: str | Path,
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    indexes = repo.load_all()
    stale_sources = [item for item in indexes.sources if item.freshness_status == "stale"]
    stale_source_keys = {item.source_key for item in stale_sources}
    blocked_source_keys = {
        item.source_key
        for item in indexes.sources
        if item.quality_status in {"blocked", "rejected"}
    }
    stale_claims = [
        item
        for item in indexes.claims
        if item.status in {"stale", "conflicted"}
        or bool(stale_source_keys.intersection(item.source_keys))
        or bool(blocked_source_keys.intersection(item.source_keys))
        or any(chunk.status in {"stale", "blocked"} for chunk in repo.chunks_for_claim(item.claim_key))
    ]
    stale_chunks = [
        item
        for item in indexes.evidence_chunks
        if item.status in {"stale", "blocked"}
        or item.source_key in stale_source_keys
        or item.source_key in blocked_source_keys
    ]
    stale_claim_keys = {item.claim_key for item in stale_claims}
    stale_artifacts = [
        item
        for item in indexes.artifact_lineage
        if item.promotion_state == "stale"
        or bool(item.stale_reasons)
        or bool(stale_claim_keys.intersection({_normalize_reference_key(reference) for reference in item.claims}))
        or bool(stale_source_keys.intersection({_normalize_reference_key(reference) for reference in item.sources}))
    ]

    nodes: list[dict[str, Any]] = []
    for source in stale_sources:
        nodes.append(
            {
                "id": f"source:{source.source_key}",
                "type": "source",
                "label": source.title,
                "status": source.freshness_status,
                "qualityStatus": source.quality_status,
                "recordKey": source.source_key,
            }
        )
    for claim in stale_claims:
        nodes.append(
            {
                "id": f"claim:{claim.claim_key}",
                "type": "claim",
                "label": claim.claim_text,
                "status": claim.status,
                "recordKey": claim.claim_key,
            }
        )
    for chunk in stale_chunks:
        nodes.append(
            {
                "id": f"chunk:{chunk.chunk_key}",
                "type": "chunk",
                "label": chunk.metadata.get("source_title") or chunk.chunk_key,
                "status": chunk.status,
                "recordKey": chunk.chunk_key,
                "sourceKey": chunk.source_key,
            }
        )
    for artifact in stale_artifacts:
        nodes.append(
            {
                "id": f"artifact:{artifact.artifact_path}",
                "type": "artifact",
                "label": artifact.title,
                "status": artifact.promotion_state,
                "recordKey": artifact.artifact_path,
                "staleReasons": list(artifact.stale_reasons),
            }
        )

    stale_node_ids = {item["id"] for item in nodes}
    edges = [
        {
            "from": edge.from_id,
            "to": edge.to_id,
            "relationship": edge.relationship,
            "edgeClass": edge.edge_class,
            "edgeKey": edge.edge_key,
            "sourceRecordKey": edge.source_record_key,
            "targetRecordKey": edge.target_record_key,
            "metadata": dict(edge.metadata),
        }
        for edge in repo.load_integrity_edges()
        if edge.from_id in stale_node_ids and edge.to_id in stale_node_ids
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "staleSourceCount": len(stale_sources),
            "staleClaimCount": len(stale_claims),
            "staleArtifactCount": len(stale_artifacts),
            "staleChunkCount": len(stale_chunks),
        },
    }


def hybrid_retrieve(
    project_root: str | Path,
    query: str,
    *,
    limit: int = 10,
    artifact_types: list[str] | None = None,
    claim_statuses: list[str] | None = None,
    source_freshness: list[str] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_stale: bool = False,
    include_blocked: bool = False,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    return repo.hybrid_retrieve(
        query,
        limit=limit,
        artifact_types=artifact_types,
        claim_statuses=claim_statuses,
        source_freshness=source_freshness,
        date_from=date_from,
        date_to=date_to,
        include_stale=include_stale,
        include_blocked=include_blocked,
    )


def evaluate_retrieval_benchmark(
    project_root: str | Path,
    benchmark_cases: list[dict[str, Any]],
    *,
    limit: int = 10,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    per_case: list[dict[str, Any]] = []
    hybrid_hits = 0
    vector_hits = 0

    for case in benchmark_cases:
        query = str(case.get("query") or "").strip()
        expected_record_keys = {str(item) for item in case.get("expectedRecordKeys") or [] if str(item).strip()}
        expected_record_types = {str(item) for item in case.get("expectedRecordTypes") or [] if str(item).strip()}
        case_limit = int(case.get("limit") or limit)

        hybrid = repo.hybrid_retrieve(query, limit=case_limit, expand_explicit=True)
        vector_only = repo.hybrid_retrieve(query, limit=case_limit, expand_explicit=False)

        def _matched_keys(payload: dict[str, Any]) -> set[str]:
            results = payload.get("results") or []
            matches = []
            for item in results:
                if expected_record_types and item.get("recordType") not in expected_record_types:
                    continue
                matches.append(str(item.get("recordKey")))
            return set(matches)

        hybrid_match = bool(expected_record_keys.intersection(_matched_keys(hybrid)))
        vector_match = bool(expected_record_keys.intersection(_matched_keys(vector_only)))
        hybrid_hits += int(hybrid_match)
        vector_hits += int(vector_match)
        per_case.append(
            {
                "query": query,
                "expectedRecordKeys": sorted(expected_record_keys),
                "expectedRecordTypes": sorted(expected_record_types),
                "hybridHit": hybrid_match,
                "vectorOnlyHit": vector_match,
                "hybridResults": hybrid.get("results", []),
                "vectorOnlyResults": vector_only.get("results", []),
            }
        )

    total_cases = len(benchmark_cases)
    hybrid_recall = (hybrid_hits / total_cases) if total_cases else 0.0
    vector_recall = (vector_hits / total_cases) if total_cases else 0.0
    return {
        "cases": per_case,
        "summary": {
            "caseCount": total_cases,
            "hybridHits": hybrid_hits,
            "vectorOnlyHits": vector_hits,
            "hybridRecallAtK": hybrid_recall,
            "vectorOnlyRecallAtK": vector_recall,
            "hybridOutperformsVectorOnly": hybrid_hits > vector_hits,
        },
    }


def evaluate_claim_verification_cases(
    project_root: str | Path,
    benchmark_cases: list[dict[str, Any]],
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    per_case: list[dict[str, Any]] = []
    passed_cases = 0

    claim_index = {claim.claim_key: claim for claim in repo.load_claims()}
    for case in benchmark_cases:
        claim_key = str(case.get("claimKey") or "").strip()
        expected_status = str(case.get("expectedStatus") or "").strip()
        expected_evidence_complete = bool(case.get("expectedEvidenceComplete"))
        claim = claim_index.get(claim_key)
        if claim is None:
            per_case.append(
                {
                    "claimKey": claim_key,
                    "passed": False,
                    "error": f"Unknown claim_key: {claim_key}",
                }
            )
            continue
        evidence_complete = bool(claim.evidence_paths or claim.source_keys or claim.evidence_chunk_keys) and claim.evidence_kind != "semantic_suggestion"
        passed = (claim.status == expected_status) and (evidence_complete == expected_evidence_complete)
        passed_cases += int(passed)
        per_case.append(
            {
                "claimKey": claim_key,
                "expectedStatus": expected_status,
                "actualStatus": claim.status,
                "expectedEvidenceComplete": expected_evidence_complete,
                "actualEvidenceComplete": evidence_complete,
                "passed": passed,
            }
        )

    total_cases = len(benchmark_cases)
    return {
        "cases": per_case,
        "summary": {
            "caseCount": total_cases,
            "passedCases": passed_cases,
            "failedCases": total_cases - passed_cases,
        },
    }


def evaluate_artifact_trust_cases(
    project_root: str | Path,
    benchmark_cases: list[dict[str, Any]],
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    passed_cases = 0

    for case in benchmark_cases:
        manifest = case.get("manifest")
        if manifest is None:
            raise ValueError("artifact trust benchmark cases require a manifest")
        action = str(case.get("action") or "artifact_generation")
        expected_blocked = bool(case.get("expectedBlocked"))
        expected_artifacts = {str(item) for item in case.get("expectedBlockingArtifacts") or [] if str(item).strip()}

        gate = evaluate_integrity_gate(project_root, manifest, action=action, plan_root=plan_root)
        actual_artifacts = set(gate.get("blockingArtifacts") or [])
        passed = (gate["blocked"] == expected_blocked) and expected_artifacts.issubset(actual_artifacts)
        passed_cases += int(passed)
        per_case.append(
            {
                "action": action,
                "expectedBlocked": expected_blocked,
                "actualBlocked": bool(gate["blocked"]),
                "expectedBlockingArtifacts": sorted(expected_artifacts),
                "actualBlockingArtifacts": sorted(actual_artifacts),
                "passed": passed,
            }
        )

    total_cases = len(benchmark_cases)
    return {
        "cases": per_case,
        "summary": {
            "caseCount": total_cases,
            "passedCases": passed_cases,
            "failedCases": total_cases - passed_cases,
        },
    }


def evaluate_reproducibility_cases(
    project_root: str | Path,
    benchmark_cases: list[dict[str, Any]],
    *,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    per_case: list[dict[str, Any]] = []
    passed_cases = 0

    for case in benchmark_cases:
        outputs = dict(case.get("outputs") or {})
        run_id = str(case.get("runId") or "rerun-verification")
        scope = str(case.get("scope") or "health")
        expected_status = str(case.get("expectedStatus") or "").strip()
        expected_artifact_states = {
            str(path): str(state)
            for path, state in dict(case.get("expectedArtifactStates") or {}).items()
            if str(path).strip()
        }

        result = apply_reproducibility_rerun(
            project_root,
            outputs,
            run_id=run_id,
            scope=scope,
            plan_root=plan_root,
        )
        repo = get_integrity_repo(project_root, plan_root=plan_root)
        artifact_index = {item.artifact_path: item for item in repo.load_artifact_lineage()}
        actual_artifact_states = {
            path: artifact_index[path].promotion_state
            for path in expected_artifact_states
            if path in artifact_index
        }
        passed = result["status"] == expected_status and actual_artifact_states == expected_artifact_states
        passed_cases += int(passed)
        per_case.append(
            {
                "runId": run_id,
                "scope": scope,
                "expectedStatus": expected_status,
                "actualStatus": result["status"],
                "expectedArtifactStates": expected_artifact_states,
                "actualArtifactStates": actual_artifact_states,
                "passed": passed,
            }
        )

    total_cases = len(benchmark_cases)
    return {
        "cases": per_case,
        "summary": {
            "caseCount": total_cases,
            "passedCases": passed_cases,
            "failedCases": total_cases - passed_cases,
        },
    }


def evaluate_default_integrity_benchmark_corpus(
    project_root: str | Path,
    *,
    retrieval_limit: int = 10,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    corpus = seed_default_integrity_benchmark_corpus(project_root)
    retrieval = evaluate_retrieval_benchmark(
        project_root,
        corpus["retrievalCases"],
        limit=retrieval_limit,
        plan_root=plan_root,
    )
    claims = evaluate_claim_verification_cases(
        project_root,
        corpus["claimVerificationCases"],
        plan_root=plan_root,
    )
    artifacts = evaluate_artifact_trust_cases(
        project_root,
        corpus["artifactTrustCases"],
        plan_root=plan_root,
    )
    reproducibility = evaluate_reproducibility_cases(
        project_root,
        corpus["reproducibilityCases"],
        plan_root=plan_root,
    )
    total_cases = (
        retrieval["summary"]["caseCount"]
        + claims["summary"]["caseCount"]
        + artifacts["summary"]["caseCount"]
        + reproducibility["summary"]["caseCount"]
    )
    passed_cases = (
        retrieval["summary"]["hybridHits"]
        + claims["summary"]["passedCases"]
        + artifacts["summary"]["passedCases"]
        + reproducibility["summary"]["passedCases"]
    )
    return {
        "metadata": corpus["metadata"],
        "retrieval": retrieval,
        "claims": claims,
        "artifacts": artifacts,
        "reproducibility": reproducibility,
        "summary": {
            "caseCount": total_cases,
            "passedCases": passed_cases,
            "failedCases": total_cases - passed_cases,
            "hybridOutperformsVectorOnly": retrieval["summary"]["hybridOutperformsVectorOnly"],
        },
    }


def promote_artifact(
    project_root: str | Path,
    manifest: Any,
    artifact_path: str,
    *,
    target_state: str,
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    records = repo.load_artifact_lineage()
    wanted = next((item for item in records if item.artifact_path == artifact_path), None)
    if wanted is None:
        raise KeyError(f"Unknown artifact_path: {artifact_path}")

    current_state = wanted.promotion_state
    allowed_targets = ALLOWED_PROMOTION_TRANSITIONS.get(current_state, set())
    if target_state != current_state and target_state not in allowed_targets:
        raise ValueError(f"Invalid promotion transition: {current_state} -> {target_state}")

    gate = evaluate_integrity_gate(project_root, manifest, action="artifact_generation", plan_root=plan_root)
    artifact_claim_keys = {_normalize_reference_key(reference) for reference in wanted.claims}
    artifact_run_ids = {_normalize_reference_key(reference) for reference in wanted.verification_runs}
    blocked_by_gate = (
        artifact_path in set(gate.get("blockingArtifacts") or [])
        or bool(artifact_claim_keys.intersection(set(gate.get("blockingClaims") or [])))
        or bool(artifact_run_ids.intersection(set(gate.get("blockingVerificationRuns") or [])))
    )
    trusted_target = target_state in {"partially_verified", "verified"}
    if trusted_target and wanted.artifact_type != "dataset":
        ontology_duckdb = Path(project_root) / ".ontology" / "onto.duckdb"
        hydration_meta = Path(project_root) / ".ontology" / ".rail_hydration.json"
        if not ontology_duckdb.exists() or not hydration_meta.exists():
            gate = {
                **gate,
                "blocked": True,
                "reasons": list(dict.fromkeys([
                    *[str(item) for item in (gate.get("reasons") or [])],
                    "Ontology hydration must exist before non-dataset artifacts can be promoted as trusted outputs.",
                ])),
                "blockingArtifacts": list(dict.fromkeys([
                    *[str(item) for item in (gate.get("blockingArtifacts") or [])],
                    artifact_path,
                ])),
            }
            blocked_by_gate = True
        elif not _duckdb_has_populated_rows(ontology_duckdb):
            gate = {
                **gate,
                "blocked": True,
                "reasons": list(dict.fromkeys([
                    *[str(item) for item in (gate.get("reasons") or [])],
                    "Ontology artifact exists but does not contain populated rows.",
                ])),
                "blockingArtifacts": list(dict.fromkeys([
                    *[str(item) for item in (gate.get("blockingArtifacts") or [])],
                    artifact_path,
                ])),
            }
            blocked_by_gate = True
    if gate["blocked"] and blocked_by_gate:
        return {
            "status": "blocked",
            "artifact": wanted.model_dump(mode="json"),
            "targetState": target_state,
            "gate": gate,
        }

    updated_records = []
    updated_artifact = wanted
    for record in records:
        if record.artifact_path != artifact_path:
            updated_records.append(record)
            continue
        updated_artifact = repo._normalize_timestamps(
            record.model_copy(
                update={
                    "promotion_state": target_state,
                    "stale_reasons": [] if target_state in {"partially_verified", "verified"} else record.stale_reasons,
                    "stale_marked_at": None if target_state in {"partially_verified", "verified"} else record.stale_marked_at,
                }
            ),
            preserve_created_at=record.created_at,
        )
        updated_records.append(updated_artifact)
    repo.write_artifact_lineage(updated_records)
    return {
        "status": "promoted",
        "artifact": updated_artifact.model_dump(mode="json"),
        "targetState": target_state,
        "gate": gate,
    }


def apply_reproducibility_rerun(
    project_root: str | Path,
    reproduced_outputs: dict[str, str | bytes],
    *,
    run_id: str = "rerun-verification",
    scope: str = "health",
    plan_root: str = "research_plan",
) -> dict[str, Any]:
    repo = get_integrity_repo(project_root, plan_root=plan_root)
    root = Path(project_root).resolve()
    artifact_paths = sorted(reproduced_outputs.keys())
    indexes = repo.load_all()
    artifact_index = {item.artifact_path: item for item in indexes.artifact_lineage}

    checks: list[dict[str, Any]] = []
    blockers: list[str] = []
    matched_paths: list[str] = []

    def _hash_bytes(value: bytes) -> str:
        return hashlib.sha1(value).hexdigest()

    def _to_bytes(value: str | bytes) -> bytes:
        return value if isinstance(value, bytes) else value.encode("utf-8")

    for artifact_path in artifact_paths:
        lineage = artifact_index.get(artifact_path)
        if lineage is None:
            blockers.append(f"Artifact `{artifact_path}` is not recorded in artifact lineage.")
            checks.append({"artifact_path": artifact_path, "status": "missing_lineage"})
            continue
        if lineage.reproducibility_mode in {"manual", "non_reproducible"}:
            blockers.append(
                f"Artifact `{artifact_path}` is labeled `{lineage.reproducibility_mode}` and cannot be rerun deterministically."
            )
            checks.append(
                {
                    "artifact_path": artifact_path,
                    "status": "non_reproducible",
                    "reproducibility_mode": lineage.reproducibility_mode,
                }
            )
            continue
        if not lineage.inputs or not lineage.scripts:
            blockers.append(f"Artifact `{artifact_path}` is missing reproducibility metadata.")
            checks.append({"artifact_path": artifact_path, "status": "missing_reproducibility_metadata"})
            continue
        actual_path = root / artifact_path
        if not actual_path.exists():
            blockers.append(f"Artifact `{artifact_path}` does not exist on disk.")
            checks.append({"artifact_path": artifact_path, "status": "missing_output"})
            continue

        expected_bytes = _to_bytes(reproduced_outputs[artifact_path])
        actual_bytes = actual_path.read_bytes()
        if actual_bytes == expected_bytes:
            matched_paths.append(artifact_path)
            checks.append(
                {
                    "artifact_path": artifact_path,
                    "status": "matched",
                    "actual_hash": _hash_bytes(actual_bytes),
                    "reproduced_hash": _hash_bytes(expected_bytes),
                }
            )
            continue

        diff_text = ""
        try:
            actual_text = actual_bytes.decode("utf-8")
            expected_text = expected_bytes.decode("utf-8")
            diff_text = "\n".join(
                difflib.unified_diff(
                    actual_text.splitlines(),
                    expected_text.splitlines(),
                    fromfile=f"actual:{artifact_path}",
                    tofile=f"reproduced:{artifact_path}",
                    lineterm="",
                )
            )
        except UnicodeDecodeError:
            diff_text = "binary output differs"
        blockers.append(f"Artifact `{artifact_path}` did not reproduce exactly.")
        checks.append(
            {
                "artifact_path": artifact_path,
                "status": "diff",
                "actual_hash": _hash_bytes(actual_bytes),
                "reproduced_hash": _hash_bytes(expected_bytes),
                "diff": diff_text[:4000],
            }
        )

    status = "passed" if not blockers else "failed"
    verification = repo.upsert_verification_run(
        {
            "run_id": run_id,
            "scope": scope,
            "loop_type": "analysis_reproducibility",
            "status": status,
            "checks": checks,
            "artifacts_checked": artifact_paths,
            "claims_checked": [],
            "artifact_paths": artifact_paths,
            "blockers": blockers,
        }
    )

    records = repo.load_artifact_lineage()
    updated_artifacts: list[ArtifactLineageRecord] = []
    wanted = set(artifact_paths)
    for idx, record in enumerate(records):
        if record.artifact_path not in wanted:
            continue
        verification_refs = list(record.verification_runs)
        ref = f"research_plan/state/verification_runs.json#{run_id}"
        if ref not in verification_refs:
            verification_refs.append(ref)
        if status == "passed":
            updated = record.model_copy(
                update={
                    "verification_runs": verification_refs,
                    "promotion_state": "partially_verified" if record.promotion_state == "stale" else record.promotion_state,
                    "stale_reasons": [reason for reason in record.stale_reasons if not reason.startswith("rerun_diff:")],
                    "stale_marked_at": None if record.artifact_path in matched_paths else record.stale_marked_at,
                }
            )
        else:
            stale_reasons = [reason for reason in record.stale_reasons if not reason.startswith("rerun_diff:")]
            stale_reasons.append(f"rerun_diff:{run_id}")
            updated = record.model_copy(
                update={
                    "verification_runs": verification_refs,
                    "promotion_state": "blocked" if record.promotion_state != "stale" else "stale",
                    "stale_reasons": stale_reasons,
                }
            )
        updated = repo._normalize_timestamps(updated, preserve_created_at=record.created_at)
        records[idx] = updated
        updated_artifacts.append(updated)
    if updated_artifacts:
        repo.write_artifact_lineage(records)
    if status == "passed":
        repo.clear_artifact_stale(matched_paths, promotion_state="partially_verified")

    return {
        "verificationRun": verification.model_dump(mode="json"),
        "artifacts": [item.model_dump(mode="json") for item in repo.load_artifact_lineage() if item.artifact_path in wanted],
        "status": status,
        "matchedArtifacts": matched_paths,
        "blockers": blockers,
    }


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

    affected_artifacts = _order_artifacts_by_dependencies(list(all_affected_artifacts.values()))
    affected_paths = [item.artifact_path for item in affected_artifacts]
    stale_paths = [
        item.artifact_path
        for item in affected_artifacts
        if item.promotion_state == "stale" or item.stale_reasons
    ]

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
    "list_source_summaries",
    "get_source_detail",
    "list_claim_summaries",
    "get_claim_detail",
    "get_artifact_detail",
    "get_integrity_dependency_graph",
    "hybrid_retrieve",
    "evaluate_retrieval_benchmark",
    "evaluate_default_integrity_benchmark_corpus",
    "evaluate_claim_verification_cases",
    "evaluate_artifact_trust_cases",
    "evaluate_reproducibility_cases",
    "promote_artifact",
    "apply_reproducibility_rerun",
    "get_stale_dependency_graph",
    "mark_script_change_and_list_stale",
    "apply_source_freshness_policy",
    "summarize_agent_workflow_health",
    "update_assumption_and_mark_stale",
    "update_source_and_mark_stale",
    "evaluate_integrity_gate",
    "build_rerun_plan",
    "build_batch_rerun_plan",
]
