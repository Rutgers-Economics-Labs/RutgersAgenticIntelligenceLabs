from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


AssumptionStatus = Literal["active", "needs_review", "superseded", "rejected"]
SourceQualityStatus = Literal["candidate", "validated", "blocked", "rejected"]
SourceFreshnessStatus = Literal["unknown", "fresh", "needs_refresh", "stale"]
SourceAdmissibilityStatus = Literal["observed", "derived", "estimated", "synthetic", "missing"]
SourceImpactLevel = Literal["low", "normal", "high", "critical"]
ClaimStatus = Literal["draft", "supported", "unsupported", "needs_evidence", "superseded", "stale", "conflicted"]
EvidenceKind = Literal["direct", "derived", "contextual", "semantic_suggestion"]
CandidateStatus = Literal["candidate", "promoted", "rejected"]
ConflictStatus = Literal["open", "reviewing", "resolved", "dismissed"]
PromotionState = Literal[
    "exploratory",
    "draft",
    "needs_evidence",
    "partially_verified",
    "verified",
    "stale",
    "blocked",
]
VerificationStatus = Literal["pending", "passed", "failed", "blocked"]
VerificationLoopType = Literal["claim_evidence", "source_freshness", "analysis_reproducibility"]
ReproducibilityMode = Literal["deterministic", "manual", "non_reproducible"]

STATE_FILE_NAMES = {
    "assumptions": "assumptions.json",
    "sources": "sources.json",
    "claims": "claims.json",
    "source_candidates": "source_candidates.json",
    "claim_candidates": "claim_candidates.json",
    "entity_candidates": "entity_candidates.json",
    "conflicts": "conflicts.json",
    "artifact_lineage": "artifact_lineage.json",
    "verification_runs": "verification_runs.json",
    "evidence_chunks": "evidence_chunks.json",
    "integrity_edges": "integrity_edges.json",
}


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str | None):
    from datetime import datetime, timezone

    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _stringify_timestamp(value: Any) -> str | None:
    from datetime import datetime, timezone

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = _parse_timestamp(str(value))
        if parsed is None:
            return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_source_path(file_name: str) -> str:
    return f"research_plan/state/{file_name}"


def _normalize_legacy_claim_record(record: dict[str, Any]) -> dict[str, Any]:
    if "claim_key" in record and "claim_text" in record:
        return record
    if "claim_id" not in record and "claim" not in record:
        return record
    artifact_entries = record.get("artifacts") if isinstance(record.get("artifacts"), list) else []
    artifact_paths = [
        str(item.get("path")).strip()
        for item in artifact_entries
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    notes = str(record.get("notes") or "").strip()
    caveats = [notes] if notes else []
    scope = str(record.get("scope") or "").strip()
    if scope:
        caveats.append(f"legacy_scope:{scope}")
    confidence_value = record.get("confidence")
    confidence: float | None = None
    if isinstance(confidence_value, (int, float)):
        confidence = float(confidence_value)
    status_value = str(record.get("status") or "").strip().lower()
    status = status_value if status_value in {"draft", "supported", "unsupported", "needs_evidence", "superseded", "stale", "conflicted"} else "needs_evidence"
    return {
        "claim_key": str(record.get("claim_id") or "").strip() or _normalize_reference_key(str(record.get("claim") or "legacy-claim")),
        "claim_text": str(record.get("claim") or record.get("claim_text") or "").strip() or "Legacy claim candidate",
        "artifact_path": artifact_paths[0] if artifact_paths else None,
        "evidence_paths": artifact_paths,
        "status": status,
        "confidence": confidence,
        "caveats": caveats,
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def _normalize_reference_key(reference: str) -> str:
    return reference.split("#", 1)[-1].strip()


def _tokenize_text(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _token_counts(text: str) -> Counter[str]:
    return Counter(_tokenize_text(text))


def _cosine_from_counters(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    overlap = set(left).intersection(right)
    if not overlap:
        return 0.0
    numerator = sum(left[token] * right[token] for token in overlap)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return float(numerator / (left_norm * right_norm))


EMBEDDING_DIMENSION = 256
EMBEDDING_MODEL = "token_hash_v1"
MIN_SEMANTIC_SCORE = 0.05


def _hash_embedding(text: str, *, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = [0.0] * dimension
    for token in _tokenize_text(text):
        digest = hashlib.sha1(token.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:8], "big") % dimension
        sign = 1.0 if (digest[8] % 2 == 0) else -1.0
        vector[slot] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if not norm:
        return vector
    return [value / norm for value in vector]


def _cosine_from_vectors(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(l * r for l, r in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def _semantic_score(
    query_text: str,
    record_text: str,
    *,
    query_embedding: list[float] | None = None,
    record_embedding: list[float] | None = None,
) -> float:
    token_score = _cosine_from_counters(_token_counts(query_text), _token_counts(record_text))
    vector_score = _cosine_from_vectors(
        query_embedding or _hash_embedding(query_text),
        record_embedding or _hash_embedding(record_text),
    )
    return max(token_score, vector_score)


class AssumptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_key: str
    title: str
    value: str
    status: AssumptionStatus = "active"
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["assumptions"]))
    affected_paths: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    source_type: str
    title: str
    url_or_path: str
    origin: str | None = None
    acquired_at: str | None = None
    access_method: str | None = None
    freshness_status: SourceFreshnessStatus = "unknown"
    admissibility_status: SourceAdmissibilityStatus | None = None
    impact_level: SourceImpactLevel = "normal"
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality_notes: str | None = None
    retrieved_at: str | None = None
    license: str | None = None
    quality_status: SourceQualityStatus = "candidate"
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["sources"]))
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ClaimRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_key: str
    claim_text: str
    artifact_path: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    evidence_chunk_keys: list[str] = Field(default_factory=list)
    source_keys: list[str] = Field(default_factory=list)
    contradicts_claim_keys: list[str] = Field(default_factory=list)
    evidence_kind: EvidenceKind | None = None
    status: ClaimStatus = "draft"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["claims"]))
    caveats: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SourceCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    title: str
    url_or_path: str
    source_type_hint: str = "url"
    status: CandidateStatus = "candidate"
    discovered_in_paths: list[str] = Field(default_factory=list)
    snippet: str | None = None
    related_claim_candidate_keys: list[str] = Field(default_factory=list)
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["source_candidates"]))
    created_at: str | None = None
    updated_at: str | None = None


class ClaimCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    claim_text: str
    status: CandidateStatus = "candidate"
    discovered_in_paths: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    source_candidate_keys: list[str] = Field(default_factory=list)
    snippet: str | None = None
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["claim_candidates"]))
    created_at: str | None = None
    updated_at: str | None = None


class EntityCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_key: str
    name: str
    entity_type_hint: str = "unknown"
    status: CandidateStatus = "candidate"
    discovered_in_paths: list[str] = Field(default_factory=list)
    mention_count: int = Field(default=1, ge=0)
    snippet: str | None = None
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["entity_candidates"]))
    created_at: str | None = None
    updated_at: str | None = None


class ConflictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_key: str
    left_ref: str
    right_ref: str
    conflict_type: str
    status: ConflictStatus = "open"
    explanation: str | None = None
    recommended_resolution: str | None = None
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["conflicts"]))
    created_at: str | None = None
    updated_at: str | None = None


class ArtifactLineageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_path: str
    artifact_type: str
    title: str
    promotion_state: PromotionState = "draft"
    reproducibility_mode: ReproducibilityMode | None = None
    inputs: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    verification_commands: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    verification_runs: list[str] = Field(default_factory=list)
    stale_reasons: list[str] = Field(default_factory=list)
    stale_marked_at: str | None = None
    generated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class VerificationRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    scope: str | None = None
    loop_type: VerificationLoopType = "analysis_reproducibility"
    task_id: str | None = None
    agent_session_id: str | None = None
    status: VerificationStatus
    checks: list[dict[str, Any]] = Field(default_factory=list)
    artifacts_checked: list[str] = Field(default_factory=list)
    claims_checked: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["verification_runs"]))
    created_at: str | None = None
    updated_at: str | None = None


def _normalize_legacy_verification_run_record(record: dict[str, Any]) -> dict[str, Any]:
    if "run_id" in record:
        normalized = dict(record)
        for key in ("timestamp", "agent_role", "check_type", "command", "failures", "notes"):
            normalized.pop(key, None)
        return normalized

    legacy_keys = {"timestamp", "agent_role", "check_type", "command", "failures", "notes"}
    if not legacy_keys.intersection(record):
        return record

    status = str(record.get("status") or "pending")
    scope = str(record.get("scope") or record.get("agent_role") or "verification")
    check_type = str(record.get("check_type") or "legacy_verification")
    timestamp = _stringify_timestamp(record.get("timestamp")) or _utc_now()
    failures = [str(item) for item in (record.get("failures") or []) if str(item).strip()]
    notes = str(record.get("notes") or "").strip()
    command = str(record.get("command") or "").strip()
    raw_key = json.dumps(record, sort_keys=True, default=str)
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:10]
    normalized_check_type = "-".join(_tokenize_text(check_type)) or "legacy-verification"
    normalized_scope = "-".join(_tokenize_text(scope)) or "verification"

    details: list[str] = []
    if notes:
        details.append(notes)
    details.extend(failures)

    return {
        "run_id": f"legacy-{normalized_scope}-{normalized_check_type}-{digest}",
        "scope": scope,
        "loop_type": "analysis_reproducibility",
        "status": status,
        "checks": [
            {
                "name": check_type,
                "status": status,
                "command": command or None,
                "details": details,
            }
        ],
        "artifacts_checked": [str(item) for item in (record.get("artifacts_checked") or []) if str(item).strip()],
        "claims_checked": [str(item) for item in (record.get("claims_checked") or []) if str(item).strip()],
        "artifact_paths": [str(item) for item in (record.get("artifact_paths") or []) if str(item).strip()],
        "blockers": failures if status in {"failed", "blocked"} else [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }


class EvidenceChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_key: str
    source_key: str
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["evidence_chunks"]))
    text: str
    ordinal: int
    char_count: int = Field(ge=0)
    content_hash: str
    embedding_model: str = EMBEDDING_MODEL
    embedding: list[float] = Field(default_factory=list)
    chunk_type: str = "text"
    status: Literal["active", "stale", "blocked"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class IntegrityEdgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_key: str
    from_id: str
    to_id: str
    relationship: str
    edge_class: Literal["explicit"] = "explicit"
    source_record_key: str | None = None
    target_record_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class IntegrityIndexes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[AssumptionRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    source_candidates: list[SourceCandidateRecord] = Field(default_factory=list)
    claim_candidates: list[ClaimCandidateRecord] = Field(default_factory=list)
    entity_candidates: list[EntityCandidateRecord] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    artifact_lineage: list[ArtifactLineageRecord] = Field(default_factory=list)
    verification_runs: list[VerificationRunRecord] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunkRecord] = Field(default_factory=list)
    integrity_edges: list[IntegrityEdgeRecord] = Field(default_factory=list)


def build_source_state(
    source: SourceRecord,
    *,
    dependent_claim_count: int = 0,
    dependent_artifact_count: int = 0,
    chunk_count: int = 0,
) -> dict[str, Any]:
    quality_blocked = source.quality_status in {"blocked", "rejected"}
    admissibility_status = source.admissibility_status
    if admissibility_status is None:
        provenance = source.provenance or {}
        if provenance.get("synthetic"):
            admissibility_status = "synthetic"
        elif provenance.get("estimated"):
            admissibility_status = "estimated"
        elif provenance.get("missing"):
            admissibility_status = "missing"
        elif provenance.get("derived_from") or provenance.get("derivedFrom"):
            admissibility_status = "derived"
        else:
            admissibility_status = "observed"
    admissible = admissibility_status in {"observed", "derived"} and not quality_blocked
    return {
        "freshnessStatus": source.freshness_status,
        "qualityStatus": source.quality_status,
        "admissibilityStatus": admissibility_status,
        "isFresh": source.freshness_status == "fresh" and not quality_blocked,
        "isStale": source.freshness_status == "stale",
        "needsRefresh": source.freshness_status == "needs_refresh",
        "isBlocked": quality_blocked,
        "isAdmissible": admissible,
        "dependentClaimCount": dependent_claim_count,
        "dependentArtifactCount": dependent_artifact_count,
        "chunkCount": chunk_count,
    }


def _has_explicit_source_promotion_provenance(provenance: dict[str, Any] | None) -> bool:
    if not provenance:
        return False
    return bool(
        provenance.get("text")
        or provenance.get("url")
        or provenance.get("path")
        or provenance.get("config_path")
        or provenance.get("retrieved_at")
        or provenance.get("acquired_at")
        or provenance.get("derived_from")
        or provenance.get("derivedFrom")
    )


def _normalize_validated_source_quality(
    *,
    quality_status: str,
    freshness_status: str,
    admissibility_status: str | None,
    provenance: dict[str, Any] | None,
) -> str:
    if quality_status != "validated":
        return quality_status
    if admissibility_status not in {"observed", "derived"}:
        return "candidate"
    if not _has_explicit_source_promotion_provenance(provenance):
        return "candidate"
    if admissibility_status == "derived" and not ((provenance or {}).get("derived_from") or (provenance or {}).get("derivedFrom")):
        return "candidate"
    if freshness_status in {"", "unknown"}:
        return "candidate"
    return quality_status


def _infer_source_admissibility_from_config(raw: dict[str, Any]) -> str:
    explicit = str(raw.get("admissibility_status") or raw.get("admissibilityStatus") or "").strip().lower()
    if explicit:
        if explicit not in {"observed", "derived", "estimated", "synthetic", "missing"}:
            raise ValueError(
                "Source config admissibility_status must be one of observed, derived, estimated, synthetic, or missing."
            )
        return explicit
    if raw.get("synthetic"):
        return "synthetic"
    if raw.get("estimated"):
        return "estimated"
    if raw.get("missing"):
        return "missing"
    if raw.get("derived_from") or raw.get("derivedFrom"):
        return "derived"
    return "observed"


def _normalize_artifact_record_for_write(
    record: ArtifactLineageRecord,
    *,
    project_root: Path,
    valid_source_keys: set[str],
    valid_assumption_keys: set[str],
    valid_claim_keys: set[str],
    valid_verification_run_keys: set[str],
) -> ArtifactLineageRecord:
    normalized_inputs = [path for path in record.inputs if path and (project_root / path).exists()]
    normalized_scripts = [path for path in record.scripts if path and (project_root / path).exists()]
    normalized_sources = [
        ref for ref in record.sources if _normalize_reference_key(ref) in valid_source_keys
    ]
    normalized_assumptions = [
        ref for ref in record.assumptions if _normalize_reference_key(ref) in valid_assumption_keys
    ]
    normalized_claims = [
        ref for ref in record.claims if _normalize_reference_key(ref) in valid_claim_keys
    ]
    normalized_verification_runs = [
        ref for ref in record.verification_runs if _normalize_reference_key(ref) in valid_verification_run_keys
    ]
    has_workflow_support = bool(normalized_inputs or normalized_scripts or normalized_verification_runs)
    promotion_state = record.promotion_state
    if promotion_state == "verified" and not normalized_verification_runs:
        promotion_state = "partially_verified" if has_workflow_support else "draft"
    if promotion_state == "partially_verified" and not has_workflow_support:
        promotion_state = "draft"
    return record.model_copy(
        update={
            "inputs": normalized_inputs,
            "scripts": normalized_scripts,
            "sources": normalized_sources,
            "assumptions": normalized_assumptions,
            "claims": normalized_claims,
            "verification_runs": normalized_verification_runs,
            "promotion_state": promotion_state,
        }
    )


def _normalize_verification_run_record_for_write(
    record: VerificationRunRecord,
    *,
    project_root: Path,
) -> VerificationRunRecord:
    normalized_artifact_paths = [
        path for path in record.artifact_paths if path and (project_root / path).exists()
    ]
    normalized_artifacts_checked = [
        path for path in record.artifacts_checked if path and (project_root / path).exists()
    ]
    status = record.status
    if status == "passed" and not normalized_artifact_paths:
        status = "pending"
    return record.model_copy(
        update={
            "artifact_paths": normalized_artifact_paths,
            "artifacts_checked": normalized_artifacts_checked,
            "status": status,
        }
    )


def _normalize_evidence_chunk_record_for_write(
    record: EvidenceChunkRecord,
    *,
    source_index: dict[str, SourceRecord],
) -> EvidenceChunkRecord | None:
    source = source_index.get(record.source_key)
    if source is None:
        return None
    status: Literal["active", "stale", "blocked"]
    if source.quality_status in {"blocked", "rejected"}:
        status = "blocked"
    elif source.freshness_status == "stale":
        status = "stale"
    else:
        status = "active"
    metadata = dict(record.metadata or {})
    metadata.update(
        {
            "source_title": source.title,
            "source_type": source.source_type,
            "url_or_path": source.url_or_path,
            "origin": source.origin,
            "freshness_status": source.freshness_status,
            "quality_status": source.quality_status,
        }
    )
    return record.model_copy(
        update={
            "char_count": len(record.text),
            "content_hash": hashlib.sha1(record.text.encode("utf-8")).hexdigest(),
            "embedding_model": EMBEDDING_MODEL,
            "embedding": _hash_embedding(record.text),
            "chunk_type": str(source.provenance.get("chunk_type") or record.chunk_type or "text"),
            "status": status,
            "metadata": metadata,
        }
    )


def build_claim_state(
    claim: ClaimRecord,
    *,
    contradictory_claim_count: int = 0,
    source_count: int = 0,
    chunk_count: int = 0,
    artifact_count: int = 0,
    verification_run_count: int = 0,
) -> dict[str, Any]:
    evidence_complete = bool(claim.evidence_paths or claim.source_keys or claim.evidence_chunk_keys) and claim.evidence_kind != "semantic_suggestion"
    return {
        "status": claim.status,
        "evidenceComplete": evidence_complete,
        "isExplicitEvidence": claim.status == "supported" and evidence_complete,
        "hasContradictions": contradictory_claim_count > 0,
        "sourceCount": source_count,
        "chunkCount": chunk_count,
        "artifactCount": artifact_count,
        "verificationRunCount": verification_run_count,
        "caveatCount": len(claim.caveats),
        "openQuestionCount": len(claim.open_questions),
    }


def build_artifact_trust_summary(
    artifact: ArtifactLineageRecord,
    *,
    verification_status: str,
    artifact_blocked: bool = False,
    gate_reasons: list[str] | None = None,
    eligible_transitions: list[str] | None = None,
    promotable_targets: list[str] | None = None,
    blocking_claims: list[str] | None = None,
    blocking_sources: list[str] | None = None,
    blocking_artifacts: list[str] | None = None,
    blocking_verification_runs: list[str] | None = None,
) -> dict[str, Any]:
    stale_reasons = list(artifact.stale_reasons)
    artifact_stale = artifact.promotion_state == "stale" or bool(stale_reasons)
    blocking_claims = sorted(set(blocking_claims or []))
    blocking_sources = sorted(set(blocking_sources or []))
    blocking_artifacts = sorted(set(blocking_artifacts or []))
    blocking_verification_runs = sorted(set(blocking_verification_runs or []))
    gate_reasons = list(gate_reasons or [])
    eligible_transitions = list(eligible_transitions or [])
    promotable_targets = list(promotable_targets or [])
    has_evidence = bool(artifact.claims or artifact.sources)
    has_fresh_sources = not any(reason.startswith("source_stale:") for reason in stale_reasons)
    is_reproducible = artifact.reproducibility_mode in {"manual", "deterministic"} or bool(
        artifact.inputs and artifact.scripts and artifact.verification_commands and artifact.verification_runs
    )
    is_trusted = artifact.promotion_state in {"partially_verified", "verified"} and not artifact_blocked and not artifact_stale
    if is_trusted:
        next_action = "Trust state is current."
    elif artifact_blocked:
        next_action = "Resolve blocking claims, sources, or verification runs before promotion."
    elif artifact_stale:
        next_action = "Rerun dependent analyses and clear stale reasons before promotion."
    elif not has_evidence:
        next_action = "Attach claims or sources so the artifact has explicit lineage."
    elif not is_reproducible:
        next_action = "Record inputs, scripts, and verification runs or mark the artifact manual."
    elif promotable_targets:
        next_action = f"Eligible for promotion to {promotable_targets[0]}."
    else:
        next_action = "Trust state is current."
    return {
        "currentState": artifact.promotion_state,
        "verificationStatus": verification_status,
        "isTrusted": is_trusted,
        "isBlocked": artifact_blocked,
        "isStale": artifact_stale,
        "hasEvidence": has_evidence,
        "hasFreshSources": has_fresh_sources,
        "isReproducible": is_reproducible,
        "staleReasons": stale_reasons,
        "blockingReasons": gate_reasons if artifact_blocked else [],
        "eligibleTransitions": eligible_transitions,
        "promotableTargets": promotable_targets,
        "blockingClaims": blocking_claims,
        "blockingSources": blocking_sources,
        "blockingArtifacts": blocking_artifacts,
        "blockingVerificationRuns": blocking_verification_runs,
        "recommendedNextAction": next_action,
    }


class ResearchIntegrityRepo:
    def __init__(self, project_root: str | Path, plan_root: str = "research_plan"):
        self.project_root = Path(project_root).resolve()
        self.plan_root = plan_root
        self.state_root = self.project_root / plan_root / "state"

    def ensure_files_exist(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        for file_name in STATE_FILE_NAMES.values():
            path = self.state_root / file_name
            if not path.exists():
                path.write_text("[]\n", encoding="utf-8")

    def assumptions_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["assumptions"]

    def sources_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["sources"]

    def claims_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["claims"]

    def source_candidates_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["source_candidates"]

    def claim_candidates_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["claim_candidates"]

    def entity_candidates_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["entity_candidates"]

    def conflicts_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["conflicts"]

    def artifact_lineage_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["artifact_lineage"]

    def verification_runs_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["verification_runs"]

    def evidence_chunks_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["evidence_chunks"]

    def integrity_edges_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["integrity_edges"]

    def compiled_truth_report_path(self) -> Path:
        return self.state_root / "compiled_truth_report.json"

    def artifact_support_matrix_path(self) -> Path:
        return self.state_root / "artifact_support_matrix.json"

    def paper_alignment_report_path(self) -> Path:
        return self.state_root / "paper_alignment_report.md"

    def compiled_truth_summary_path(self) -> Path:
        return self.state_root / "compiled_truth_report.md"

    @staticmethod
    def source_node_id(source_key: str) -> str:
        return f"source:{source_key}"

    @staticmethod
    def claim_node_id(claim_key: str) -> str:
        return f"claim:{claim_key}"

    @staticmethod
    def chunk_node_id(chunk_key: str) -> str:
        return f"chunk:{chunk_key}"

    @staticmethod
    def artifact_node_id(record: ArtifactLineageRecord) -> str:
        prefix = "dataset" if record.artifact_type == "dataset" else "artifact"
        return f"{prefix}:{record.artifact_path}"

    def load_integrity_edge_index(
        self,
        edges: list[IntegrityEdgeRecord] | None = None,
    ) -> tuple[dict[str, list[IntegrityEdgeRecord]], dict[str, list[IntegrityEdgeRecord]]]:
        outgoing: dict[str, list[IntegrityEdgeRecord]] = {}
        incoming: dict[str, list[IntegrityEdgeRecord]] = {}
        for edge in edges or self.load_integrity_edges():
            outgoing.setdefault(edge.from_id, []).append(edge)
            incoming.setdefault(edge.to_id, []).append(edge)
        return outgoing, incoming

    def neighbors_for_node(
        self,
        node_id: str,
        *,
        relationship: str | None = None,
        direction: Literal["out", "in", "both"] = "out",
        edges: list[IntegrityEdgeRecord] | None = None,
    ) -> list[IntegrityEdgeRecord]:
        outgoing, incoming = self.load_integrity_edge_index(edges)
        selected: list[IntegrityEdgeRecord] = []
        if direction in {"out", "both"}:
            selected.extend(outgoing.get(node_id, []))
        if direction in {"in", "both"}:
            selected.extend(incoming.get(node_id, []))
        if relationship is None:
            return selected
        return [edge for edge in selected if edge.relationship == relationship]

    def load_all(self) -> IntegrityIndexes:
        return IntegrityIndexes(
            assumptions=self.load_assumptions(),
            sources=self.load_sources(),
            claims=self.load_claims(),
            source_candidates=self.load_source_candidates(),
            claim_candidates=self.load_claim_candidates(),
            entity_candidates=self.load_entity_candidates(),
            conflicts=self.load_conflicts(),
            artifact_lineage=self.load_artifact_lineage(),
            verification_runs=self.load_verification_runs(),
            evidence_chunks=self.load_evidence_chunks(),
            integrity_edges=self.load_integrity_edges(),
        )

    def rebuild_all(self) -> IntegrityIndexes:
        indexes = self.load_all()
        self.write_assumptions(indexes.assumptions)
        self.write_sources(indexes.sources)
        self.write_claims(indexes.claims)
        self.write_source_candidates(indexes.source_candidates)
        self.write_claim_candidates(indexes.claim_candidates)
        self.write_entity_candidates(indexes.entity_candidates)
        self.write_artifact_lineage(indexes.artifact_lineage)
        self.write_verification_runs(indexes.verification_runs)
        self.write_evidence_chunks(indexes.evidence_chunks)
        self.rebuild_conflicts()
        self.rebuild_integrity_edges()
        return self.load_all()

    def compile_truth_report(
        self,
        *,
        alignment_paths: list[str] | None = None,
        write_files: bool = False,
    ) -> dict[str, Any]:
        self.ensure_files_exist()
        self.rebuild_all()
        indexes = self.load_all()

        source_index = {item.source_key: item for item in indexes.sources}
        claim_index = {item.claim_key: item for item in indexes.claims}
        artifact_index = {item.artifact_path: item for item in indexes.artifact_lineage}
        verification_index = {item.run_id: item for item in indexes.verification_runs}

        source_details: list[dict[str, Any]] = []
        claim_details: list[dict[str, Any]] = []
        artifact_support_matrix: list[dict[str, Any]] = []
        source_gaps: list[dict[str, Any]] = []

        freshness_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        claim_bucket_counts: dict[str, int] = {}
        artifact_bucket_counts: dict[str, int] = {}

        for source in indexes.sources:
            dependent_claims = self.claims_for_source(source.source_key)
            dependent_artifacts = self.artifacts_for_source(source.source_key)
            chunk_count = len(self.chunks_for_source(source.source_key))
            source_state = build_source_state(
                source,
                dependent_claim_count=len(dependent_claims),
                dependent_artifact_count=len(dependent_artifacts),
                chunk_count=chunk_count,
            )
            compiled_status = "current"
            if source_state["isBlocked"]:
                compiled_status = "blocked"
            elif source_state["isStale"]:
                compiled_status = "stale"
            elif source_state["needsRefresh"]:
                compiled_status = "needs_refresh"
            source_details.append(
                {
                    "sourceKey": source.source_key,
                    "title": source.title,
                    "sourceType": source.source_type,
                    "freshnessStatus": source.freshness_status,
                    "qualityStatus": source.quality_status,
                    "compiledStatus": compiled_status,
                    "state": source_state,
                    "qualityNotes": source.quality_notes,
                    "provenance": source.provenance,
                }
            )
            freshness_counts[source.freshness_status] = freshness_counts.get(source.freshness_status, 0) + 1
            quality_counts[source.quality_status] = quality_counts.get(source.quality_status, 0) + 1
            if compiled_status != "current" or source.quality_notes:
                source_gaps.append(
                    {
                        "kind": "source",
                        "sourceKey": source.source_key,
                        "status": compiled_status,
                        "message": source.quality_notes
                        or f"Source is {compiled_status.replace('_', ' ')}.",
                    }
                )

        for claim in indexes.claims:
            artifacts = self.artifacts_for_claim(claim.claim_key)
            chunks = self.chunks_for_claim(claim.claim_key)
            contradictory_count = len(claim.contradicts_claim_keys)
            verification_run_count = sum(
                1
                for run in indexes.verification_runs
                if claim.claim_key in run.claims_checked
            )
            claim_state = build_claim_state(
                claim,
                contradictory_claim_count=contradictory_count,
                source_count=len(claim.source_keys),
                chunk_count=len(chunks),
                artifact_count=len(artifacts),
                verification_run_count=verification_run_count,
            )
            linked_sources = [source_index[key] for key in claim.source_keys if key in source_index]
            blocked_sources = [source.source_key for source in linked_sources if source.quality_status in {"blocked", "rejected"}]
            stale_sources = [source.source_key for source in linked_sources if source.freshness_status == "stale"]
            if blocked_sources or claim.status == "conflicted":
                compiled_status = "blocked"
            elif stale_sources or claim.status == "stale":
                compiled_status = "stale"
            elif claim.status in {"draft", "unsupported", "needs_evidence"}:
                compiled_status = claim.status
            elif not claim_state["evidenceComplete"]:
                compiled_status = "needs_evidence"
            elif claim.evidence_kind in {"derived", "contextual"} or claim.caveats or claim.open_questions:
                compiled_status = "partially_verified"
            else:
                compiled_status = "supported"
            claim_details.append(
                {
                    "claimKey": claim.claim_key,
                    "claimText": claim.claim_text,
                    "ledgerStatus": claim.status,
                    "compiledStatus": compiled_status,
                    "evidenceKind": claim.evidence_kind,
                    "confidence": claim.confidence,
                    "sourceKeys": claim.source_keys,
                    "evidencePaths": claim.evidence_paths,
                    "evidenceChunkKeys": claim.evidence_chunk_keys,
                    "artifactPaths": [artifact.artifact_path for artifact in artifacts],
                    "caveats": claim.caveats,
                    "openQuestions": claim.open_questions,
                    "state": claim_state,
                }
            )
            claim_bucket_counts[compiled_status] = claim_bucket_counts.get(compiled_status, 0) + 1
            if compiled_status in {"needs_evidence", "stale", "blocked", "draft", "unsupported"} or claim.caveats or claim.open_questions:
                source_gaps.append(
                    {
                        "kind": "claim",
                        "claimKey": claim.claim_key,
                        "status": compiled_status,
                        "message": "; ".join([*claim.caveats, *claim.open_questions])
                        or f"Claim is {compiled_status.replace('_', ' ')}.",
                    }
                )

        for artifact in indexes.artifact_lineage:
            linked_claims = [claim_index[_normalize_reference_key(ref)] for ref in artifact.claims if _normalize_reference_key(ref) in claim_index]
            linked_sources = [source_index[_normalize_reference_key(ref)] for ref in artifact.sources if _normalize_reference_key(ref) in source_index]
            linked_runs = [verification_index[_normalize_reference_key(ref)] for ref in artifact.verification_runs if _normalize_reference_key(ref) in verification_index]
            blocking_claims = [
                claim["claimKey"]
                for claim in claim_details
                if claim["claimKey"] in {item.claim_key for item in linked_claims}
                and claim["compiledStatus"] in {"needs_evidence", "stale", "blocked", "draft", "unsupported"}
            ]
            blocking_sources = [
                source.source_key
                for source in linked_sources
                if source.freshness_status == "stale" or source.quality_status in {"blocked", "rejected"}
            ]
            blocking_runs = [
                run.run_id
                for run in linked_runs
                if run.status in {"failed", "blocked"}
            ]
            verification_status = "pending"
            if blocking_runs:
                verification_status = "blocked"
            elif linked_runs and all(run.status == "passed" for run in linked_runs):
                verification_status = "passed"
            elif linked_runs and any(run.status == "failed" for run in linked_runs):
                verification_status = "failed"
            artifact_blocked = bool(blocking_claims or blocking_sources or blocking_runs)
            gate_reasons = [f"claim:{key}" for key in blocking_claims]
            gate_reasons.extend(f"source:{key}" for key in blocking_sources)
            gate_reasons.extend(f"verification_run:{key}" for key in blocking_runs)
            promotable_targets: list[str] = []
            if not artifact_blocked and not artifact.stale_reasons:
                if artifact.promotion_state in {"draft", "exploratory", "needs_evidence"}:
                    promotable_targets.append("partially_verified")
                elif artifact.promotion_state == "partially_verified" and verification_status == "passed":
                    promotable_targets.append("verified")
            trust_summary = build_artifact_trust_summary(
                artifact,
                verification_status=verification_status,
                artifact_blocked=artifact_blocked,
                gate_reasons=gate_reasons,
                eligible_transitions=promotable_targets,
                promotable_targets=promotable_targets,
                blocking_claims=blocking_claims,
                blocking_sources=blocking_sources,
                blocking_verification_runs=blocking_runs,
            )
            compiled_status = artifact.promotion_state
            if trust_summary["isBlocked"]:
                compiled_status = "blocked"
            elif trust_summary["isStale"]:
                compiled_status = "stale"
            elif artifact.promotion_state == "verified" and not trust_summary["isTrusted"]:
                compiled_status = "partially_verified"
            artifact_support_matrix.append(
                {
                    "artifactPath": artifact.artifact_path,
                    "title": artifact.title,
                    "artifactType": artifact.artifact_type,
                    "compiledStatus": compiled_status,
                    "linkedClaims": [claim.claim_key for claim in linked_claims],
                    "linkedSources": [source.source_key for source in linked_sources],
                    "linkedVerificationRuns": [run.run_id for run in linked_runs],
                    "reproducibilityMode": artifact.reproducibility_mode,
                    "trustSummary": trust_summary,
                }
            )
            artifact_bucket_counts[compiled_status] = artifact_bucket_counts.get(compiled_status, 0) + 1
            if compiled_status in {"blocked", "stale", "needs_evidence", "draft", "exploratory"}:
                source_gaps.append(
                    {
                        "kind": "artifact",
                        "artifactPath": artifact.artifact_path,
                        "status": compiled_status,
                        "message": trust_summary["recommendedNextAction"],
                    }
                )

        alignment = self._build_alignment_report(
            alignment_paths=alignment_paths or [],
            claim_details=claim_details,
            source_details=source_details,
        )
        if alignment["issues"]:
            source_gaps.extend(
                {
                    "kind": "paper_alignment",
                    "path": issue["path"],
                    "status": issue["severity"],
                    "message": issue["message"],
                }
                for issue in alignment["issues"]
            )

        project_status = "verified"
        if artifact_bucket_counts.get("blocked"):
            project_status = "blocked"
        elif artifact_bucket_counts.get("stale"):
            project_status = "stale"
        elif artifact_bucket_counts.get("needs_evidence"):
            project_status = "needs_evidence"
        elif artifact_bucket_counts.get("partially_verified"):
            project_status = "partially_verified"
        elif artifact_bucket_counts.get("draft") or artifact_bucket_counts.get("exploratory"):
            project_status = "draft"

        claim_groups = {
            "supported": [item for item in claim_details if item["compiledStatus"] == "supported"],
            "partiallyVerified": [item for item in claim_details if item["compiledStatus"] == "partially_verified"],
            "needsEvidence": [item for item in claim_details if item["compiledStatus"] == "needs_evidence"],
            "stale": [item for item in claim_details if item["compiledStatus"] == "stale"],
            "blocked": [item for item in claim_details if item["compiledStatus"] == "blocked"],
            "draft": [item for item in claim_details if item["compiledStatus"] in {"draft", "unsupported"}],
        }
        artifact_groups = {
            "verified": [item for item in artifact_support_matrix if item["compiledStatus"] == "verified"],
            "partiallyVerified": [item for item in artifact_support_matrix if item["compiledStatus"] == "partially_verified"],
            "needsEvidence": [item for item in artifact_support_matrix if item["compiledStatus"] == "needs_evidence"],
            "stale": [item for item in artifact_support_matrix if item["compiledStatus"] == "stale"],
            "blocked": [item for item in artifact_support_matrix if item["compiledStatus"] == "blocked"],
            "draft": [item for item in artifact_support_matrix if item["compiledStatus"] in {"draft", "exploratory"}],
        }
        source_groups = {
            "current": [item for item in source_details if item["compiledStatus"] == "current"],
            "needsRefresh": [item for item in source_details if item["compiledStatus"] == "needs_refresh"],
            "stale": [item for item in source_details if item["compiledStatus"] == "stale"],
            "blocked": [item for item in source_details if item["compiledStatus"] == "blocked"],
        }
        candidate_summary = {
            "sourceCandidates": [item.model_dump(mode="json") for item in indexes.source_candidates],
            "claimCandidates": [item.model_dump(mode="json") for item in indexes.claim_candidates],
            "entityCandidates": [item.model_dump(mode="json") for item in indexes.entity_candidates],
        }
        conflict_summary = [item.model_dump(mode="json") for item in indexes.conflicts]

        report = {
            "generatedAt": _utc_now(),
            "projectRoot": str(self.project_root),
            "summary": {
                "projectStatus": project_status,
                "claimCount": len(claim_details),
                "artifactCount": len(artifact_support_matrix),
                "sourceCount": len(source_details),
                "sourceCandidateCount": len(indexes.source_candidates),
                "claimCandidateCount": len(indexes.claim_candidates),
                "entityCandidateCount": len(indexes.entity_candidates),
                "conflictCount": len(indexes.conflicts),
                "verificationRunCount": len(indexes.verification_runs),
                "claimStatusCounts": claim_bucket_counts,
                "artifactStatusCounts": artifact_bucket_counts,
                "sourceFreshnessCounts": freshness_counts,
                "sourceQualityCounts": quality_counts,
                "paperAlignmentIssueCount": len(alignment["issues"]),
            },
            "claims": claim_groups,
            "artifacts": artifact_groups,
            "sources": source_groups,
            "claimDetails": claim_details,
            "sourceDetails": source_details,
            "artifactSupportMatrix": artifact_support_matrix,
            "candidates": candidate_summary,
            "conflicts": conflict_summary,
            "sourceGaps": source_gaps,
            "paperAlignment": alignment,
        }
        if write_files:
            self._write_compiled_truth_outputs(report)
        return report

    def load_assumptions(self) -> list[AssumptionRecord]:
        return self._load_records(self.assumptions_path(), AssumptionRecord)

    def write_assumptions(self, records: list[AssumptionRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.assumptions_path(), records, AssumptionRecord)
        self.rebuild_integrity_edges()

    def upsert_assumption(self, record: AssumptionRecord | dict[str, Any]) -> AssumptionRecord:
        stored = self._normalize_timestamps(AssumptionRecord.model_validate(record))
        records = self.load_assumptions()
        index = {item.assumption_key: item for item in records}
        existing = index.get(stored.assumption_key)
        if existing and stored.created_at is None:
            stored.created_at = existing.created_at
        merged = self._normalize_timestamps(stored, preserve_created_at=existing.created_at if existing else None)
        index[merged.assumption_key] = merged
        self.write_assumptions(list(index.values()))
        return merged

    def update_assumption(self, assumption_key: str, **changes: Any) -> AssumptionRecord:
        records = self.load_assumptions()
        for idx, record in enumerate(records):
            if record.assumption_key != assumption_key:
                continue
            updated = record.model_copy(update=changes)
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            self.write_assumptions(records)
            self.mark_artifacts_stale_for_assumption(updated.assumption_key)
            return updated
        raise KeyError(f"Unknown assumption_key: {assumption_key}")

    def load_sources(self) -> list[SourceRecord]:
        return self._load_records(self.sources_path(), SourceRecord)

    def write_sources(self, records: list[SourceRecord] | list[dict[str, Any]]) -> None:
        normalized_records: list[SourceRecord] = []
        for record in records:
            normalized = SourceRecord.model_validate(record)
            normalized_records.append(
                normalized.model_copy(
                    update={
                        "quality_status": _normalize_validated_source_quality(
                            quality_status=normalized.quality_status,
                            freshness_status=normalized.freshness_status,
                            admissibility_status=normalized.admissibility_status,
                            provenance=normalized.provenance,
                        )
                    }
                )
            )
        self._write_records(self.sources_path(), normalized_records, SourceRecord)
        self.rebuild_integrity_edges()

    def upsert_source(self, record: SourceRecord | dict[str, Any]) -> SourceRecord:
        normalized = SourceRecord.model_validate(record)
        normalized = normalized.model_copy(
            update={
                "quality_status": _normalize_validated_source_quality(
                    quality_status=normalized.quality_status,
                    freshness_status=normalized.freshness_status,
                    admissibility_status=normalized.admissibility_status,
                    provenance=normalized.provenance,
                )
            }
        )
        stored = self._upsert_by_key(self.load_sources, self.write_sources, SourceRecord, "source_key", normalized)
        self.rebuild_chunks_for_source(stored.source_key)
        return stored

    def update_source(self, source_key: str, **changes: Any) -> tuple[SourceRecord, list[ClaimRecord], list[ArtifactLineageRecord]]:
        records = self.load_sources()
        for idx, record in enumerate(records):
            if record.source_key != source_key:
                continue
            updated = record.model_copy(update=changes)
            updated = updated.model_copy(
                update={
                    "quality_status": _normalize_validated_source_quality(
                        quality_status=updated.quality_status,
                        freshness_status=updated.freshness_status,
                        admissibility_status=updated.admissibility_status,
                        provenance=updated.provenance,
                    )
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            self.write_sources(records)
            self.rebuild_chunks_for_source(updated.source_key)
            if updated.quality_status in {"blocked", "rejected"}:
                conflicted_claims = self.mark_claims_conflicted_for_source(updated.source_key)
                blocked_artifacts = self.mark_artifacts_blocked_for_source(updated.source_key)
                return updated, conflicted_claims, blocked_artifacts
            if updated.freshness_status == "stale":
                self._set_chunk_status_for_source(updated.source_key, status="stale")
                stale_claims = self.mark_claims_stale_for_source(updated.source_key)
                stale_artifacts = self.mark_artifacts_stale_for_source(updated.source_key)
                return updated, stale_claims, stale_artifacts
            else:
                self._set_chunk_status_for_source(updated.source_key, status="active")
                refreshed_claims = self.clear_claims_stale_for_source(updated.source_key)
                refreshed_artifacts = self.clear_artifacts_stale_for_source(updated.source_key)
                return updated, refreshed_claims, refreshed_artifacts
        raise KeyError(f"Unknown source_key: {source_key}")

    def load_claims(self) -> list[ClaimRecord]:
        return self._load_records(self.claims_path(), ClaimRecord)

    def _normalize_claim_record_for_write(self, record: ClaimRecord | dict[str, Any]) -> ClaimRecord:
        normalized = ClaimRecord.model_validate(record)
        known_source_keys = {item.source_key for item in self.load_sources()}
        known_chunk_keys = {item.chunk_key for item in self.load_evidence_chunks()}
        valid_evidence_paths = [
            path
            for path in normalized.evidence_paths
            if path and (self.project_root / path).exists()
        ]
        valid_source_keys = [key for key in normalized.source_keys if key in known_source_keys]
        valid_chunk_keys = [key for key in normalized.evidence_chunk_keys if key in known_chunk_keys]
        normalized = normalized.model_copy(
            update={
                "evidence_paths": valid_evidence_paths,
                "source_keys": valid_source_keys,
                "evidence_chunk_keys": valid_chunk_keys,
            }
        )
        if normalized.status != "supported":
            return normalized
        expected_status = self._default_claim_status(
            list(normalized.evidence_paths),
            list(normalized.source_keys),
            list(normalized.evidence_chunk_keys),
            normalized.evidence_kind,
        )
        if expected_status == "supported":
            return normalized
        return normalized.model_copy(update={"status": expected_status})

    def write_claims(self, records: list[ClaimRecord] | list[dict[str, Any]]) -> None:
        normalized_records = [self._normalize_claim_record_for_write(record) for record in records]
        self._write_records(self.claims_path(), normalized_records, ClaimRecord)
        self.rebuild_integrity_edges()

    def upsert_claim(self, record: ClaimRecord | dict[str, Any]) -> ClaimRecord:
        stored = self._upsert_by_key(
            self.load_claims,
            self.write_claims,
            ClaimRecord,
            "claim_key",
            self._normalize_claim_record_for_write(record),
        )
        self.reconcile_claim_conflicts()
        self.reconcile_artifact_claim_support()
        return self.get_claim(stored.claim_key) or stored

    def load_source_candidates(self) -> list[SourceCandidateRecord]:
        return self._load_records(self.source_candidates_path(), SourceCandidateRecord)

    def write_source_candidates(self, records: list[SourceCandidateRecord] | list[dict[str, Any]]) -> None:
        source_records = self.load_sources()
        normalized_records: list[SourceCandidateRecord] = []
        for record in records:
            normalized = SourceCandidateRecord.model_validate(record)
            if normalized.status == "promoted":
                has_canonical_source = any(
                    str(source.provenance.get("sourceCandidateKey")) == normalized.candidate_key
                    or source.url_or_path == normalized.url_or_path
                    for source in source_records
                )
                if not has_canonical_source:
                    normalized = normalized.model_copy(update={"status": "candidate"})
            normalized_records.append(normalized)
        self._write_records(self.source_candidates_path(), normalized_records, SourceCandidateRecord)

    def upsert_source_candidate(self, record: SourceCandidateRecord | dict[str, Any]) -> SourceCandidateRecord:
        normalized = SourceCandidateRecord.model_validate(record)
        if normalized.status == "promoted":
            has_canonical_source = any(
                str(source.provenance.get("sourceCandidateKey")) == normalized.candidate_key
                or source.url_or_path == normalized.url_or_path
                for source in self.load_sources()
            )
            if not has_canonical_source:
                normalized = normalized.model_copy(update={"status": "candidate"})
        return self._upsert_by_key(
            self.load_source_candidates,
            self.write_source_candidates,
            SourceCandidateRecord,
            "candidate_key",
            normalized,
        )

    def get_source_candidate(self, candidate_key: str) -> SourceCandidateRecord | None:
        for record in self.load_source_candidates():
            if record.candidate_key == candidate_key:
                return record
        return None

    def load_claim_candidates(self) -> list[ClaimCandidateRecord]:
        return self._load_records(self.claim_candidates_path(), ClaimCandidateRecord)

    def write_claim_candidates(self, records: list[ClaimCandidateRecord] | list[dict[str, Any]]) -> None:
        claim_records = self.load_claims()
        normalized_records: list[ClaimCandidateRecord] = []
        for record in records:
            normalized = ClaimCandidateRecord.model_validate(record)
            if normalized.status == "promoted":
                has_canonical_claim = any(claim.claim_text == normalized.claim_text for claim in claim_records)
                if not has_canonical_claim:
                    normalized = normalized.model_copy(update={"status": "candidate"})
            normalized_records.append(normalized)
        self._write_records(self.claim_candidates_path(), normalized_records, ClaimCandidateRecord)

    def upsert_claim_candidate(self, record: ClaimCandidateRecord | dict[str, Any]) -> ClaimCandidateRecord:
        normalized = ClaimCandidateRecord.model_validate(record)
        if normalized.status == "promoted":
            has_canonical_claim = any(claim.claim_text == normalized.claim_text for claim in self.load_claims())
            if not has_canonical_claim:
                normalized = normalized.model_copy(update={"status": "candidate"})
        return self._upsert_by_key(
            self.load_claim_candidates,
            self.write_claim_candidates,
            ClaimCandidateRecord,
            "candidate_key",
            normalized,
        )

    def get_claim_candidate(self, candidate_key: str) -> ClaimCandidateRecord | None:
        for record in self.load_claim_candidates():
            if record.candidate_key == candidate_key:
                return record
        return None

    def load_entity_candidates(self) -> list[EntityCandidateRecord]:
        return self._load_records(self.entity_candidates_path(), EntityCandidateRecord)

    def write_entity_candidates(self, records: list[EntityCandidateRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.entity_candidates_path(), records, EntityCandidateRecord)

    def upsert_entity_candidate(self, record: EntityCandidateRecord | dict[str, Any]) -> EntityCandidateRecord:
        return self._upsert_by_key(
            self.load_entity_candidates,
            self.write_entity_candidates,
            EntityCandidateRecord,
            "candidate_key",
            record,
        )

    def load_conflicts(self) -> list[ConflictRecord]:
        return self._load_records(self.conflicts_path(), ConflictRecord)

    def _persist_conflicts(self, records: list[ConflictRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.conflicts_path(), records, ConflictRecord)

    def write_conflicts(self, records: list[ConflictRecord] | list[dict[str, Any]]) -> None:
        self.rebuild_conflicts()

    def upsert_conflict(self, record: ConflictRecord | dict[str, Any]) -> ConflictRecord:
        normalized = ConflictRecord.model_validate(record)
        records = self.load_conflicts()
        index = {item.conflict_key: item for item in records}
        existing = index.get(normalized.conflict_key)
        if existing is None:
            raise KeyError(f"Unknown conflict_key: {normalized.conflict_key}")
        merged = self._normalize_timestamps(
            normalized,
            preserve_created_at=existing.created_at,
        )
        index[merged.conflict_key] = merged
        self._persist_conflicts(list(index.values()))
        return merged

    def get_conflict(self, conflict_key: str) -> ConflictRecord | None:
        for record in self.load_conflicts():
            if record.conflict_key == conflict_key:
                return record
        return None

    def load_artifact_lineage(self) -> list[ArtifactLineageRecord]:
        return self._load_records(self.artifact_lineage_path(), ArtifactLineageRecord)

    def write_artifact_lineage(self, records: list[ArtifactLineageRecord] | list[dict[str, Any]]) -> None:
        valid_source_keys = {item.source_key for item in self.load_sources()}
        valid_assumption_keys = {item.assumption_key for item in self.load_assumptions()}
        valid_claim_keys = {item.claim_key for item in self.load_claims()}
        valid_verification_run_keys = {item.run_id for item in self.load_verification_runs()}
        normalized_records: list[ArtifactLineageRecord] = []
        for record in records:
            normalized = ArtifactLineageRecord.model_validate(record)
            normalized_records.append(
                _normalize_artifact_record_for_write(
                    normalized,
                    project_root=self.project_root,
                    valid_source_keys=valid_source_keys,
                    valid_assumption_keys=valid_assumption_keys,
                    valid_claim_keys=valid_claim_keys,
                    valid_verification_run_keys=valid_verification_run_keys,
                )
            )
        self._write_records(self.artifact_lineage_path(), normalized_records, ArtifactLineageRecord)
        self.rebuild_integrity_edges()

    def upsert_artifact_lineage(self, record: ArtifactLineageRecord | dict[str, Any]) -> ArtifactLineageRecord:
        valid_source_keys = {item.source_key for item in self.load_sources()}
        valid_assumption_keys = {item.assumption_key for item in self.load_assumptions()}
        valid_claim_keys = {item.claim_key for item in self.load_claims()}
        valid_verification_run_keys = {item.run_id for item in self.load_verification_runs()}
        normalized = ArtifactLineageRecord.model_validate(record)
        normalized = _normalize_artifact_record_for_write(
            normalized,
            project_root=self.project_root,
            valid_source_keys=valid_source_keys,
            valid_assumption_keys=valid_assumption_keys,
            valid_claim_keys=valid_claim_keys,
            valid_verification_run_keys=valid_verification_run_keys,
        )
        stored = self._upsert_by_key(
            self.load_artifact_lineage,
            self.write_artifact_lineage,
            ArtifactLineageRecord,
            "artifact_path",
            normalized,
        )
        self.reconcile_artifact_claim_support()
        return next(
            (item for item in self.load_artifact_lineage() if item.artifact_path == stored.artifact_path),
            stored,
        )

    def load_verification_runs(self) -> list[VerificationRunRecord]:
        return self._load_records(self.verification_runs_path(), VerificationRunRecord)

    def write_verification_runs(self, records: list[VerificationRunRecord] | list[dict[str, Any]]) -> None:
        normalized_records = [
            _normalize_verification_run_record_for_write(
                VerificationRunRecord.model_validate(record),
                project_root=self.project_root,
            )
            for record in records
        ]
        self._write_records(self.verification_runs_path(), normalized_records, VerificationRunRecord)
        self.rebuild_integrity_edges()

    def upsert_verification_run(self, record: VerificationRunRecord | dict[str, Any]) -> VerificationRunRecord:
        normalized = _normalize_verification_run_record_for_write(
            VerificationRunRecord.model_validate(record),
            project_root=self.project_root,
        )
        return self._upsert_by_key(
            self.load_verification_runs,
            self.write_verification_runs,
            VerificationRunRecord,
            "run_id",
            normalized,
        )

    def load_evidence_chunks(self) -> list[EvidenceChunkRecord]:
        return self._load_records(self.evidence_chunks_path(), EvidenceChunkRecord)

    def write_evidence_chunks(self, records: list[EvidenceChunkRecord] | list[dict[str, Any]]) -> None:
        source_index = {item.source_key: item for item in self.load_sources()}
        normalized_records: list[EvidenceChunkRecord] = []
        for record in records:
            normalized = _normalize_evidence_chunk_record_for_write(
                EvidenceChunkRecord.model_validate(record),
                source_index=source_index,
            )
            if normalized is not None:
                normalized_records.append(normalized)
        self._write_records(self.evidence_chunks_path(), normalized_records, EvidenceChunkRecord)
        self.rebuild_integrity_edges()

    def load_integrity_edges(self) -> list[IntegrityEdgeRecord]:
        return self._load_records(self.integrity_edges_path(), IntegrityEdgeRecord)

    def _persist_integrity_edges(self, records: list[IntegrityEdgeRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.integrity_edges_path(), records, IntegrityEdgeRecord)

    def write_integrity_edges(self, records: list[IntegrityEdgeRecord] | list[dict[str, Any]]) -> None:
        self._persist_integrity_edges(self._compute_integrity_edges())

    def _compute_integrity_edges(self) -> list[IntegrityEdgeRecord]:
        sources = self.load_sources()
        assumptions = self.load_assumptions()
        claims = self.load_claims()
        artifacts = self.load_artifact_lineage()
        verification_runs = self.load_verification_runs()
        chunks = self.load_evidence_chunks()

        artifact_index = {row.artifact_path: row for row in artifacts}
        verification_run_index = {row.run_id: row for row in verification_runs}
        assumption_index = {row.assumption_key: row for row in assumptions}
        chunk_index = {row.chunk_key: row for row in chunks}
        source_index = {row.source_key: row for row in sources}
        claim_index = {row.claim_key: row for row in claims}

        edges: list[IntegrityEdgeRecord] = []
        seen: set[tuple[str, str, str]] = set()

        def _add_edge(
            from_id: str,
            to_id: str,
            relationship: str,
            *,
            source_record_key: str | None = None,
            target_record_key: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            dedupe_key = (from_id, relationship, to_id)
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            edges.append(
                self._ensure_record_timestamps(
                    IntegrityEdgeRecord.model_validate(
                        {
                            "edge_key": f"{from_id}|{relationship}|{to_id}",
                            "from_id": from_id,
                            "to_id": to_id,
                            "relationship": relationship,
                            "edge_class": "explicit",
                            "source_record_key": source_record_key,
                            "target_record_key": target_record_key,
                            "metadata": metadata or {},
                        }
                    )
                )
            )

        for row in chunks:
            _add_edge(
                f"source:{row.source_key}",
                f"chunk:{row.chunk_key}",
                "chunked_as",
                source_record_key=row.source_key,
                target_record_key=row.chunk_key,
                metadata={"chunkStatus": row.status, "chunkType": row.chunk_type},
            )

        for row in claims:
            for source_key in row.source_keys:
                _add_edge(
                    f"source:{source_key}",
                    f"claim:{row.claim_key}",
                    "supports",
                    source_record_key=source_key if source_key in source_index else row.claim_key,
                    target_record_key=row.claim_key,
                    metadata={"evidenceKind": row.evidence_kind or "unspecified"},
                )
            for chunk_key in row.evidence_chunk_keys:
                _add_edge(
                    f"chunk:{chunk_key}",
                    f"claim:{row.claim_key}",
                    "supports",
                    source_record_key=chunk_key if chunk_key in chunk_index else row.claim_key,
                    target_record_key=row.claim_key,
                    metadata={"evidenceKind": row.evidence_kind or "unspecified"},
                )
            for other_key in row.contradicts_claim_keys:
                _add_edge(
                    f"claim:{row.claim_key}",
                    f"claim:{other_key}",
                    "contradicts",
                    source_record_key=row.claim_key,
                    target_record_key=other_key if other_key in claim_index else row.claim_key,
                )

        for row in artifacts:
            artifact_id = self.artifact_node_id(row)
            for source_ref in row.sources:
                source_key = _normalize_reference_key(source_ref)
                _add_edge(
                    artifact_id,
                    f"source:{source_key}",
                    "derived_from",
                    source_record_key=row.artifact_path,
                    target_record_key=source_key if source_key in source_index else row.artifact_path,
                )
            for claim_ref in row.claims:
                claim_key = _normalize_reference_key(claim_ref)
                _add_edge(
                    f"claim:{claim_key}",
                    artifact_id,
                    "supports",
                    source_record_key=claim_key if claim_key in claim_index else row.artifact_path,
                    target_record_key=row.artifact_path,
                )
            for assumption_ref in row.assumptions:
                assumption_key = _normalize_reference_key(assumption_ref)
                _add_edge(
                    artifact_id,
                    f"assumption:{assumption_key}",
                    "depends_on",
                    source_record_key=row.artifact_path,
                    target_record_key=assumption_key if assumption_key in assumption_index else row.artifact_path,
                )
            for script_path in row.scripts:
                _add_edge(
                    artifact_id,
                    f"method:{script_path}",
                    "generated_by",
                    source_record_key=row.artifact_path,
                    target_record_key=script_path,
                )
            for run_ref in row.verification_runs:
                run_id = _normalize_reference_key(run_ref)
                _add_edge(
                    artifact_id,
                    f"verification_run:{run_id}",
                    "verified_by",
                    source_record_key=row.artifact_path,
                    target_record_key=run_id if run_id in verification_run_index else row.artifact_path,
                )
            for input_path in row.inputs:
                upstream = artifact_index.get(input_path)
                if upstream is not None:
                    _add_edge(
                        artifact_id,
                        self.artifact_node_id(upstream),
                        "depends_on",
                        source_record_key=row.artifact_path,
                        target_record_key=upstream.artifact_path,
                    )

        return edges

    def rebuild_integrity_edges(self) -> list[IntegrityEdgeRecord]:
        edges = self._compute_integrity_edges()
        self._persist_integrity_edges(edges)
        return edges

    def chunks_for_source(self, source_key: str) -> list[EvidenceChunkRecord]:
        return [record for record in self.load_evidence_chunks() if record.source_key == source_key]

    def rebuild_chunks_for_source(
        self,
        source_key: str,
        *,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
    ) -> list[EvidenceChunkRecord]:
        source = self.get_source(source_key)
        if source is None:
            raise KeyError(f"Unknown source_key: {source_key}")
        text = self._resolve_source_text(source)
        existing = self.load_evidence_chunks()
        retained = [record for record in existing if record.source_key != source_key]
        if not text.strip():
            self.write_evidence_chunks(retained)
            return []
        chunks = self._chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        status: Literal["active", "stale", "blocked"]
        if source.quality_status in {"blocked", "rejected"}:
            status = "blocked"
        elif source.freshness_status == "stale":
            status = "stale"
        else:
            status = "active"
        records: list[EvidenceChunkRecord] = []
        for idx, chunk_text in enumerate(chunks):
            content_hash = hashlib.sha1(chunk_text.encode("utf-8")).hexdigest()
            chunk_embedding = _hash_embedding(chunk_text)
            records.append(
                self._normalize_timestamps(
                    EvidenceChunkRecord.model_validate(
                        {
                            "chunk_key": f"{source_key}#chunk-{idx + 1:04d}",
                            "source_key": source_key,
                            "text": chunk_text,
                            "ordinal": idx,
                            "char_count": len(chunk_text),
                            "content_hash": content_hash,
                            "embedding_model": EMBEDDING_MODEL,
                            "embedding": chunk_embedding,
                            "chunk_type": str(source.provenance.get("chunk_type") or "text"),
                            "status": status,
                            "metadata": {
                                "source_title": source.title,
                                "source_type": source.source_type,
                                "url_or_path": source.url_or_path,
                                "origin": source.origin,
                                "freshness_status": source.freshness_status,
                                "quality_status": source.quality_status,
                            },
                        }
                    )
                )
            )
        self.write_evidence_chunks([*retained, *records])
        return records

    def _compute_conflicts(
        self,
        *,
        existing_by_key: dict[str, ConflictRecord] | None = None,
    ) -> list[ConflictRecord]:
        claims = self.load_claims()
        existing_by_key = existing_by_key or {item.conflict_key: item for item in self.load_conflicts()}
        conflicts: list[ConflictRecord] = []
        seen: set[str] = set()
        for claim in claims:
            for other_key in claim.contradicts_claim_keys:
                pair = tuple(sorted((claim.claim_key, other_key)))
                conflict_key = f"claim-conflict:{pair[0]}::{pair[1]}"
                if conflict_key in seen:
                    continue
                seen.add(conflict_key)
                existing = existing_by_key.get(conflict_key)
                status = existing.status if existing else "open"
                conflicts.append(
                    self._normalize_timestamps(
                        ConflictRecord.model_validate(
                            {
                                "conflict_key": conflict_key,
                                "left_ref": f"research_plan/state/claims.json#{pair[0]}",
                                "right_ref": f"research_plan/state/claims.json#{pair[1]}",
                                "conflict_type": "claim_contradiction",
                                "status": status,
                                "explanation": (existing.explanation if existing else None)
                                or "Two claims are marked as contradictory and need a resolution decision.",
                                "recommended_resolution": (existing.recommended_resolution if existing else None)
                                or "Compare methods, evidence paths, and scope; then either resolve or downgrade the affected claims.",
                            }
                        ),
                        preserve_created_at=existing.created_at if existing else None,
                    )
                )
        for conflict_key, existing in existing_by_key.items():
            if conflict_key in seen:
                continue
            if existing.status not in {"resolved", "dismissed"}:
                continue
            conflicts.append(existing)
        return conflicts

    def rebuild_conflicts(self) -> list[ConflictRecord]:
        conflicts = self._compute_conflicts()
        self._persist_conflicts(conflicts)
        return conflicts

    def promote_source_candidate(
        self,
        candidate_key: str,
        *,
        source_key: str | None = None,
        source_type: str | None = None,
        title: str | None = None,
        origin: str | None = None,
        access_method: str | None = None,
        freshness_status: SourceFreshnessStatus = "unknown",
        quality_status: SourceQualityStatus = "candidate",
        quality_notes: str | None = None,
        notes: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        candidate = self.get_source_candidate(candidate_key)
        if candidate is None:
            raise KeyError(f"Unknown source candidate: {candidate_key}")

        existing_source = next(
            (
                record
                for record in self.load_sources()
                if str(record.provenance.get("sourceCandidateKey")) == candidate_key
                or record.url_or_path == candidate.url_or_path
            ),
            None,
        )
        promoted_source_key = source_key or (
            existing_source.source_key if existing_source else self._record_key("source", candidate.url_or_path)
        )
        merged_provenance = dict(existing_source.provenance if existing_source else {})
        merged_provenance.update(provenance or {})
        merged_provenance.setdefault("sourceCandidateKey", candidate.candidate_key)
        merged_provenance.setdefault("discoveredInPaths", list(candidate.discovered_in_paths))
        merged_provenance.setdefault("promotionMethod", "candidate_promotion")
        effective_quality_status = quality_status or (existing_source.quality_status if existing_source else "candidate")
        if effective_quality_status == "validated" and not _has_explicit_source_promotion_provenance(merged_provenance):
            raise ValueError("Validated source promotion requires explicit provenance metadata.")

        source_record = SourceRecord.model_validate(
            {
                "source_key": promoted_source_key,
                "source_type": source_type or candidate.source_type_hint or (existing_source.source_type if existing_source else "document"),
                "title": title or candidate.title or (existing_source.title if existing_source else candidate.url_or_path),
                "url_or_path": candidate.url_or_path,
                "origin": origin or (existing_source.origin if existing_source else candidate.url_or_path),
                "acquired_at": existing_source.acquired_at if existing_source else None,
                "access_method": access_method or (existing_source.access_method if existing_source else "candidate_promotion"),
                "freshness_status": freshness_status or (existing_source.freshness_status if existing_source else "unknown"),
                "quality_status": effective_quality_status,
                "quality_notes": quality_notes if quality_notes is not None else (existing_source.quality_notes if existing_source else None),
                "notes": notes if notes is not None else (existing_source.notes if existing_source else candidate.snippet),
                "provenance": merged_provenance,
                "retrieved_at": existing_source.retrieved_at if existing_source else None,
                "license": existing_source.license if existing_source else None,
                "impact_level": existing_source.impact_level if existing_source else "normal",
            }
        )
        promoted_source = self.upsert_source(source_record)
        updated_candidate = self.upsert_source_candidate(
            candidate.model_copy(update={"status": "promoted"})
        )
        return {
            "status": "promoted",
            "candidate": updated_candidate.model_dump(mode="json"),
            "source": promoted_source.model_dump(mode="json"),
        }

    def promote_claim_candidate(
        self,
        candidate_key: str,
        *,
        claim_key: str | None = None,
        artifact_path: str | None = None,
        status: ClaimStatus | None = None,
        evidence_kind: EvidenceKind | None = None,
        confidence: float | None = None,
        source_keys: list[str] | None = None,
        contradicts_claim_keys: list[str] | None = None,
        caveats: list[str] | None = None,
        open_questions: list[str] | None = None,
    ) -> dict[str, Any]:
        candidate = self.get_claim_candidate(candidate_key)
        if candidate is None:
            raise KeyError(f"Unknown claim candidate: {candidate_key}")

        resolved_source_keys = sorted(set(source_keys or self._resolve_source_keys_for_claim_candidate(candidate)))
        requested_status = status
        promoted_claim_key = claim_key or self._record_key("claim", candidate.claim_text)
        existing_claim = self.get_claim(promoted_claim_key)
        resolved_evidence_kind = evidence_kind or (
            existing_claim.evidence_kind if existing_claim is not None else ("direct" if resolved_source_keys or candidate.evidence_paths else None)
        )
        if requested_status == "supported" and (
            not (resolved_source_keys or candidate.evidence_paths)
            or resolved_evidence_kind in {None, "semantic_suggestion"}
        ):
            raise ValueError(
                "Supported claims require explicit recorded evidence before claim-candidate promotion."
            )
        effective_status = status or (
            existing_claim.status
            if existing_claim is not None
            else (
                "supported"
                if resolved_evidence_kind not in {None, "semantic_suggestion"} and (resolved_source_keys or candidate.evidence_paths)
                else "needs_evidence"
            )
        )
        claim_record = ClaimRecord.model_validate(
            {
                "claim_key": promoted_claim_key,
                "claim_text": existing_claim.claim_text if existing_claim is not None else candidate.claim_text,
                "artifact_path": artifact_path if artifact_path is not None else (existing_claim.artifact_path if existing_claim is not None else None),
                "evidence_paths": sorted(set((existing_claim.evidence_paths if existing_claim is not None else []) + list(candidate.evidence_paths))),
                "evidence_chunk_keys": list(existing_claim.evidence_chunk_keys if existing_claim is not None else []),
                "source_keys": sorted(set((existing_claim.source_keys if existing_claim is not None else []) + resolved_source_keys)),
                "evidence_kind": resolved_evidence_kind,
                "status": effective_status,
                "confidence": confidence if confidence is not None else (existing_claim.confidence if existing_claim is not None else None),
                "contradicts_claim_keys": sorted(set((existing_claim.contradicts_claim_keys if existing_claim is not None else []) + list(contradicts_claim_keys or []))),
                "caveats": list(caveats if caveats is not None else (existing_claim.caveats if existing_claim is not None else [])),
                "open_questions": list(open_questions if open_questions is not None else (existing_claim.open_questions if existing_claim is not None else [])),
            }
        )
        promoted_claim = self.upsert_claim(claim_record)
        updated_candidate = self.upsert_claim_candidate(
            candidate.model_copy(update={"status": "promoted"})
        )
        unresolved_source_candidate_keys = sorted(
            key for key in candidate.source_candidate_keys if key not in set(self._source_candidate_key_map().keys())
        )
        return {
            "status": "promoted",
            "candidate": updated_candidate.model_dump(mode="json"),
            "claim": promoted_claim.model_dump(mode="json"),
            "resolvedSourceKeys": resolved_source_keys,
            "unresolvedSourceCandidateKeys": unresolved_source_candidate_keys,
        }

    def resolve_conflict(
        self,
        conflict_key: str,
        *,
        status: ConflictStatus,
        explanation: str | None = None,
        favored_claim_key: str | None = None,
        demote_other_to: ClaimStatus = "superseded",
    ) -> dict[str, Any]:
        conflict = self.get_conflict(conflict_key)
        if conflict is None:
            raise KeyError(f"Unknown conflict: {conflict_key}")
        if status not in {"resolved", "dismissed", "reviewing", "open"}:
            raise ValueError(f"Unsupported conflict status: {status}")

        updated_conflict = self.upsert_conflict(
            conflict.model_copy(
                update={
                    "status": status,
                    "explanation": explanation if explanation is not None else conflict.explanation,
                }
            )
        )
        updated_claims: list[ClaimRecord] = []

        if conflict.conflict_type == "claim_contradiction" and status in {"resolved", "dismissed"}:
            left_key = _normalize_reference_key(conflict.left_ref)
            right_key = _normalize_reference_key(conflict.right_ref)
            records = self.load_claims()
            refreshed_records: list[ClaimRecord] = []
            for record in records:
                if record.claim_key not in {left_key, right_key}:
                    refreshed_records.append(record)
                    continue
                next_status = record.status
                if status == "resolved" and favored_claim_key:
                    if record.claim_key == favored_claim_key:
                        next_status = self._default_claim_status(
                            record.evidence_paths,
                            record.source_keys,
                            record.evidence_chunk_keys,
                            record.evidence_kind,
                        )
                    else:
                        next_status = demote_other_to
                elif status == "dismissed":
                    next_status = self._default_claim_status(
                        record.evidence_paths,
                        record.source_keys,
                        record.evidence_chunk_keys,
                        record.evidence_kind,
                    )
                updated = record.model_copy(
                    update={
                        "status": next_status,
                        "contradicts_claim_keys": [
                            key
                            for key in record.contradicts_claim_keys
                            if key not in {left_key, right_key} or key == record.claim_key
                        ],
                    }
                )
                updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
                refreshed_records.append(updated)
                updated_claims.append(updated)
            self.write_claims(refreshed_records)
            self.reconcile_artifact_claim_support()
            self.rebuild_conflicts()

        return {
            "status": "resolved" if status in {"resolved", "dismissed"} else "updated",
            "conflict": updated_conflict.model_dump(mode="json"),
            "claims": [record.model_dump(mode="json") for record in updated_claims],
        }

    def extract_candidates_from_paths(
        self,
        relative_paths: list[str],
        *,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        source_candidates = [] if replace_existing else self.load_source_candidates()
        claim_candidates = [] if replace_existing else self.load_claim_candidates()
        entity_candidates = [] if replace_existing else self.load_entity_candidates()

        source_index = {item.candidate_key: item for item in source_candidates}
        claim_index = {item.candidate_key: item for item in claim_candidates}
        entity_index = {item.candidate_key: item for item in entity_candidates}

        processed_paths: list[str] = []
        discovered_sources = 0
        discovered_claims = 0
        discovered_entities = 0

        for rel_path in sorted(set(relative_paths)):
            path = self.project_root / rel_path
            if not path.exists() or not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".txt", ".tex", ".yaml", ".yml", ".json", ".csv"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if not text.strip():
                continue
            processed_paths.append(rel_path)

            url_candidates = re.findall(r"https?://[^\s)\]>\"']+", text)
            line_sources = set(url_candidates)
            for url in sorted(line_sources):
                candidate_key = self._candidate_key("source", url)
                snippet = self._first_matching_line(text, url)
                existing = source_index.get(candidate_key)
                discovered_sources += int(existing is None)
                source_index[candidate_key] = self._normalize_timestamps(
                    SourceCandidateRecord.model_validate(
                        {
                            "candidate_key": candidate_key,
                            "title": self._title_from_url(url),
                            "url_or_path": url,
                            "source_type_hint": "url",
                            "status": existing.status if existing else "candidate",
                            "discovered_in_paths": sorted(set((existing.discovered_in_paths if existing else []) + [rel_path])),
                            "snippet": snippet or (existing.snippet if existing else None),
                            "related_claim_candidate_keys": list(existing.related_claim_candidate_keys if existing else []),
                            "relevance_score": max(existing.relevance_score or 0, self._estimate_relevance(snippet or url)) if existing else self._estimate_relevance(snippet or url),
                        }
                    ),
                    preserve_created_at=existing.created_at if existing else None,
                )

            local_claim_keys: list[str] = []
            for claim_text, snippet in self._extract_claim_candidate_texts(text):
                candidate_key = self._candidate_key("claim", claim_text)
                existing = claim_index.get(candidate_key)
                discovered_claims += int(existing is None)
                source_candidate_keys = sorted(line_sources and [self._candidate_key("source", url) for url in sorted(line_sources)] or [])
                claim_index[candidate_key] = self._normalize_timestamps(
                    ClaimCandidateRecord.model_validate(
                        {
                            "candidate_key": candidate_key,
                            "claim_text": claim_text,
                            "status": existing.status if existing else "candidate",
                            "discovered_in_paths": sorted(set((existing.discovered_in_paths if existing else []) + [rel_path])),
                            "evidence_paths": sorted(set((existing.evidence_paths if existing else []) + [rel_path])),
                            "source_candidate_keys": sorted(set((existing.source_candidate_keys if existing else []) + source_candidate_keys)),
                            "snippet": snippet or (existing.snippet if existing else None),
                        }
                    ),
                    preserve_created_at=existing.created_at if existing else None,
                )
                local_claim_keys.append(candidate_key)

            for phrase, count, snippet in self._extract_entity_candidates(text):
                candidate_key = self._candidate_key("entity", phrase)
                existing = entity_index.get(candidate_key)
                discovered_entities += int(existing is None)
                mention_count = max(count, existing.mention_count if existing else 0)
                entity_index[candidate_key] = self._normalize_timestamps(
                    EntityCandidateRecord.model_validate(
                        {
                            "candidate_key": candidate_key,
                            "name": phrase,
                            "entity_type_hint": self._entity_type_hint(phrase),
                            "status": existing.status if existing else "candidate",
                            "discovered_in_paths": sorted(set((existing.discovered_in_paths if existing else []) + [rel_path])),
                            "mention_count": mention_count,
                            "snippet": snippet or (existing.snippet if existing else None),
                        }
                    ),
                    preserve_created_at=existing.created_at if existing else None,
                )

            if local_claim_keys and line_sources:
                source_keys_for_file = [self._candidate_key("source", url) for url in sorted(line_sources)]
                for source_key in source_keys_for_file:
                    source = source_index.get(source_key)
                    if source is None:
                        continue
                    source_index[source_key] = source.model_copy(
                        update={
                            "related_claim_candidate_keys": sorted(
                                set(source.related_claim_candidate_keys + local_claim_keys)
                            )
                        }
                    )

        self.write_source_candidates(list(source_index.values()))
        self.write_claim_candidates(list(claim_index.values()))
        self.write_entity_candidates(list(entity_index.values()))
        return {
            "processedPaths": processed_paths,
            "sourceCandidateCount": len(source_index),
            "claimCandidateCount": len(claim_index),
            "entityCandidateCount": len(entity_index),
            "newSourceCandidates": discovered_sources,
            "newClaimCandidates": discovered_claims,
            "newEntityCandidates": discovered_entities,
        }

    def mark_artifacts_stale_for_assumption(self, assumption_key: str) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        records = self.load_artifact_lineage()
        reason = f"assumption_changed:{assumption_key}"
        for idx, record in enumerate(records):
            keys = {_normalize_reference_key(reference) for reference in record.assumptions}
            if assumption_key not in keys:
                continue
            stale_reasons = list(record.stale_reasons)
            if reason not in stale_reasons:
                stale_reasons.append(reason)
            updated = record.model_copy(
                update={
                    "promotion_state": "stale",
                    "stale_reasons": stale_reasons,
                    "stale_marked_at": _utc_now(),
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        return changed

    def mark_claims_stale_for_source(self, source_key: str) -> list[ClaimRecord]:
        changed: list[ClaimRecord] = []
        records = self.load_claims()
        for idx, record in enumerate(records):
            if source_key not in record.source_keys:
                continue
            updated = record.model_copy(update={"status": "stale"})
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_claims(records)
        return changed

    def mark_claims_conflicted_for_source(self, source_key: str) -> list[ClaimRecord]:
        changed: list[ClaimRecord] = []
        records = self.load_claims()
        for idx, record in enumerate(records):
            if source_key not in record.source_keys:
                continue
            updated = record.model_copy(update={"status": "conflicted"})
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_claims(records)
        return changed

    def clear_claims_stale_for_source(self, source_key: str) -> list[ClaimRecord]:
        changed: list[ClaimRecord] = []
        records = self.load_claims()
        for idx, record in enumerate(records):
            if source_key not in record.source_keys:
                continue
            if record.status not in {"stale", "conflicted"}:
                continue
            updated = record.model_copy(update={"status": "supported" if (record.evidence_paths or record.source_keys or record.evidence_chunk_keys) and record.evidence_kind != "semantic_suggestion" else "needs_evidence"})
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_claims(records)
            self.reconcile_artifact_claim_support()
        return changed

    def reconcile_artifact_claim_support(self) -> list[ArtifactLineageRecord]:
        claim_index = {item.claim_key: item for item in self.load_claims()}
        records = self.load_artifact_lineage()
        changed: list[ArtifactLineageRecord] = []
        updated_records: list[ArtifactLineageRecord] = []

        def _claim_needs_evidence(record: ClaimRecord) -> bool:
            if record.status in {"draft", "unsupported", "needs_evidence"}:
                return True
            if record.status != "supported":
                return False
            if record.evidence_kind == "semantic_suggestion":
                return True
            return not bool(record.evidence_paths or record.source_keys or record.evidence_chunk_keys)

        def _restore_state(record: ArtifactLineageRecord) -> PromotionState:
            return "partially_verified" if (record.inputs or record.scripts or record.verification_runs) else "draft"

        for record in records:
            claim_keys = {_normalize_reference_key(reference) for reference in record.claims}
            unsupported_claims = sorted(
                claim_key
                for claim_key in claim_keys
                if (claim := claim_index.get(claim_key)) is not None and _claim_needs_evidence(claim)
            )
            stale_reasons = [
                reason for reason in record.stale_reasons if not reason.startswith("claim_needs_evidence:")
            ]
            next_state = record.promotion_state
            if unsupported_claims:
                for claim_key in unsupported_claims:
                    stale_reasons.append(f"claim_needs_evidence:{claim_key}")
                if record.promotion_state not in {"stale", "blocked"}:
                    next_state = "needs_evidence"
            elif len(stale_reasons) != len(record.stale_reasons) and record.promotion_state == "needs_evidence":
                next_state = _restore_state(record)

            next_marked_at = _utc_now() if stale_reasons else None
            if stale_reasons != record.stale_reasons or next_state != record.promotion_state or next_marked_at != record.stale_marked_at:
                updated = record.model_copy(
                    update={
                        "promotion_state": next_state,
                        "stale_reasons": stale_reasons,
                        "stale_marked_at": next_marked_at,
                    }
                )
                updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
                updated_records.append(updated)
                changed.append(updated)
            else:
                updated_records.append(record)

        if changed:
            self.write_artifact_lineage(updated_records)
        return changed

    def reconcile_claim_conflicts(self) -> tuple[list[ClaimRecord], list[ArtifactLineageRecord]]:
        records = self.load_claims()
        index = {item.claim_key: item for item in records}
        conflict_pairs: set[tuple[str, str]] = set()

        def _claim_has_explicit_support(record: ClaimRecord) -> bool:
            return (
                record.status == "supported"
                and bool(record.evidence_paths or record.source_keys or record.evidence_chunk_keys)
                and record.evidence_kind != "semantic_suggestion"
            )

        for record in records:
            for other_key in record.contradicts_claim_keys:
                other = index.get(other_key)
                if other is None:
                    continue
                if _claim_has_explicit_support(record) and _claim_has_explicit_support(other):
                    conflict_pairs.add(tuple(sorted((record.claim_key, other.claim_key))))

        conflicted_keys = {key for pair in conflict_pairs for key in pair}
        changed_claims: list[ClaimRecord] = []
        updated_records: list[ClaimRecord] = []
        for record in records:
            if record.claim_key in conflicted_keys:
                if record.status != "conflicted":
                    updated = record.model_copy(update={"status": "conflicted"})
                    updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
                    updated_records.append(updated)
                    changed_claims.append(updated)
                else:
                    updated_records.append(record)
            elif record.status == "conflicted":
                restored_status = "supported" if (record.evidence_paths or record.source_keys or record.evidence_chunk_keys) and record.evidence_kind != "semantic_suggestion" else "needs_evidence"
                updated = record.model_copy(update={"status": restored_status})
                updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
                updated_records.append(updated)
                changed_claims.append(updated)
            else:
                updated_records.append(record)

        if changed_claims:
            self.write_claims(updated_records)

        blocked_artifacts = self._reconcile_artifact_claim_conflicts(conflicted_keys)
        return changed_claims, blocked_artifacts

    def _reconcile_artifact_claim_conflicts(self, conflicted_claim_keys: set[str]) -> list[ArtifactLineageRecord]:
        records = self.load_artifact_lineage()
        changed: list[ArtifactLineageRecord] = []
        updated_records: list[ArtifactLineageRecord] = []
        for record in records:
            claim_keys = {_normalize_reference_key(reference) for reference in record.claims}
            conflicting_claims = sorted(claim_keys.intersection(conflicted_claim_keys))
            stale_reasons = [reason for reason in record.stale_reasons if not reason.startswith("claim_conflicted:")]
            next_state = record.promotion_state
            if conflicting_claims:
                for claim_key in conflicting_claims:
                    stale_reasons.append(f"claim_conflicted:{claim_key}")
                next_state = "blocked" if record.promotion_state != "stale" else "stale"
            elif len(stale_reasons) != len(record.stale_reasons) and record.promotion_state in {"blocked", "stale"}:
                next_state = "partially_verified" if record.inputs or record.scripts or record.verification_runs else "draft"

            if stale_reasons != record.stale_reasons or next_state != record.promotion_state:
                updated = record.model_copy(
                    update={
                        "promotion_state": next_state,
                        "stale_reasons": stale_reasons,
                        "stale_marked_at": _utc_now() if stale_reasons else None,
                    }
                )
                updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
                updated_records.append(updated)
                changed.append(updated)
            else:
                updated_records.append(record)

        if changed:
            self.write_artifact_lineage(updated_records)
        return changed

    def mark_artifacts_stale_for_source(self, source_key: str) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        stale_claim_keys = {
            claim.claim_key
            for claim in self.load_claims()
            if source_key in claim.source_keys and claim.status == "stale"
        }
        records = self.load_artifact_lineage()
        reason = f"source_changed:{source_key}"
        for idx, record in enumerate(records):
            source_keys = {_normalize_reference_key(reference) for reference in record.sources}
            claim_keys = {_normalize_reference_key(reference) for reference in record.claims}
            if source_key not in source_keys and not stale_claim_keys.intersection(claim_keys):
                continue
            stale_reasons = list(record.stale_reasons)
            if reason not in stale_reasons:
                stale_reasons.append(reason)
            updated = record.model_copy(
                update={
                    "promotion_state": "stale",
                    "stale_reasons": stale_reasons,
                    "stale_marked_at": _utc_now(),
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        self._set_chunk_status_for_source(source_key, status="stale")
        return changed

    def mark_artifacts_blocked_for_source(self, source_key: str) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        conflicted_claim_keys = {
            claim.claim_key
            for claim in self.load_claims()
            if source_key in claim.source_keys and claim.status == "conflicted"
        }
        records = self.load_artifact_lineage()
        reason = f"source_blocked:{source_key}"
        for idx, record in enumerate(records):
            source_keys = {_normalize_reference_key(reference) for reference in record.sources}
            claim_keys = {_normalize_reference_key(reference) for reference in record.claims}
            if source_key not in source_keys and not conflicted_claim_keys.intersection(claim_keys):
                continue
            stale_reasons = list(record.stale_reasons)
            if reason not in stale_reasons:
                stale_reasons.append(reason)
            updated = record.model_copy(
                update={
                    "promotion_state": "blocked",
                    "stale_reasons": stale_reasons,
                    "stale_marked_at": _utc_now(),
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        self._set_chunk_status_for_source(source_key, status="blocked")
        return changed

    def clear_artifacts_stale_for_source(self, source_key: str) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        records = self.load_artifact_lineage()
        refreshed_claim_keys = {
            claim.claim_key
            for claim in self.load_claims()
            if source_key in claim.source_keys and claim.status not in {"stale", "conflicted"}
        }
        reason_prefixes = {f"source_changed:{source_key}", f"source_blocked:{source_key}"}
        for idx, record in enumerate(records):
            source_keys = {_normalize_reference_key(reference) for reference in record.sources}
            claim_keys = {_normalize_reference_key(reference) for reference in record.claims}
            if source_key not in source_keys and not refreshed_claim_keys.intersection(claim_keys):
                continue
            stale_reasons = [reason for reason in record.stale_reasons if reason not in reason_prefixes]
            next_state = record.promotion_state
            stale_marked_at = record.stale_marked_at
            if not stale_reasons and record.promotion_state in {"stale", "blocked"}:
                next_state = "partially_verified"
                stale_marked_at = None
            updated = record.model_copy(
                update={
                    "promotion_state": next_state,
                    "stale_reasons": stale_reasons,
                    "stale_marked_at": stale_marked_at,
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        return changed

    def mark_artifacts_stale_for_script(self, script_path: str) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        records = self.load_artifact_lineage()
        reason = f"script_changed:{script_path}"
        for idx, record in enumerate(records):
            if script_path not in record.scripts:
                continue
            stale_reasons = list(record.stale_reasons)
            if reason not in stale_reasons:
                stale_reasons.append(reason)
            updated = record.model_copy(
                update={
                    "promotion_state": "stale",
                    "stale_reasons": stale_reasons,
                    "stale_marked_at": _utc_now(),
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        return changed

    def artifacts_for_assumption(self, assumption_key: str) -> list[ArtifactLineageRecord]:
        return [
            record
            for record in self.load_artifact_lineage()
            if assumption_key in {_normalize_reference_key(reference) for reference in record.assumptions}
        ]

    def claims_for_source(self, source_key: str) -> list[ClaimRecord]:
        return [record for record in self.load_claims() if source_key in record.source_keys]

    def get_source(self, source_key: str) -> SourceRecord | None:
        for record in self.load_sources():
            if record.source_key == source_key:
                return record
        return None

    def get_claim(self, claim_key: str) -> ClaimRecord | None:
        for record in self.load_claims():
            if record.claim_key == claim_key:
                return record
        return None

    def chunks_for_claim(self, claim_key: str) -> list[EvidenceChunkRecord]:
        claim = self.get_claim(claim_key)
        if claim is None:
            return []
        attached = set(claim.evidence_chunk_keys)
        return [record for record in self.load_evidence_chunks() if record.chunk_key in attached]

    def artifacts_for_claim(self, claim_key: str) -> list[ArtifactLineageRecord]:
        return [
            record
            for record in self.load_artifact_lineage()
            if claim_key in {_normalize_reference_key(reference) for reference in record.claims}
        ]

    def artifacts_for_source(self, source_key: str) -> list[ArtifactLineageRecord]:
        claim_keys = {claim.claim_key for claim in self.claims_for_source(source_key)}
        return [
            record
            for record in self.load_artifact_lineage()
            if source_key in {_normalize_reference_key(reference) for reference in record.sources}
            or bool(claim_keys.intersection({_normalize_reference_key(reference) for reference in record.claims}))
        ]

    def artifacts_for_script(self, script_path: str) -> list[ArtifactLineageRecord]:
        return [record for record in self.load_artifact_lineage() if script_path in record.scripts]

    def verification_runs_for_artifact_paths(self, artifact_paths: list[str]) -> list[VerificationRunRecord]:
        wanted = set(artifact_paths)
        return [
            record
            for record in self.load_verification_runs()
            if wanted.intersection(record.artifact_paths)
        ]

    def hybrid_retrieve(
        self,
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
        expand_explicit: bool = True,
    ) -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {
                "query": query,
                "results": [],
                "summary": {
                    "resultCount": 0,
                    "explicitEvidenceCount": 0,
                    "semanticSuggestionCount": 0,
                },
                "filters": {
                    "artifactTypes": artifact_types or [],
                    "claimStatuses": claim_statuses or [],
                    "sourceFreshness": source_freshness or [],
                    "dateFrom": date_from,
                    "dateTo": date_to,
                    "includeStale": include_stale,
                    "includeBlocked": include_blocked,
                    "expandExplicit": expand_explicit,
                },
            }

        indexes = self.load_all()
        source_index = {item.source_key: item for item in indexes.sources}
        claim_index = {item.claim_key: item for item in indexes.claims}
        artifact_index = {item.artifact_path: item for item in indexes.artifact_lineage}
        chunk_index = {item.chunk_key: item for item in indexes.evidence_chunks}
        artifact_node_ids = {
            item.artifact_path: self.artifact_node_id(item)
            for item in indexes.artifact_lineage
        }
        edges = indexes.integrity_edges
        outgoing_edges, incoming_edges = self.load_integrity_edge_index(edges)

        def _outgoing(node_id: str, relationship: str | None = None) -> list[IntegrityEdgeRecord]:
            selected = outgoing_edges.get(node_id, [])
            if relationship is None:
                return selected
            return [edge for edge in selected if edge.relationship == relationship]

        def _incoming(node_id: str, relationship: str | None = None) -> list[IntegrityEdgeRecord]:
            selected = incoming_edges.get(node_id, [])
            if relationship is None:
                return selected
            return [edge for edge in selected if edge.relationship == relationship]

        source_claims: dict[str, list[ClaimRecord]] = {}
        for source in indexes.sources:
            claims = []
            for edge in _outgoing(self.source_node_id(source.source_key), "supports"):
                claim_key = edge.to_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None:
                    claims.append(claim)
            source_claims[source.source_key] = claims

        source_artifacts: dict[str, list[ArtifactLineageRecord]] = {}
        for source in indexes.sources:
            artifacts: dict[str, ArtifactLineageRecord] = {}
            for edge in _incoming(self.source_node_id(source.source_key), "derived_from"):
                if not edge.from_id.startswith(("artifact:", "dataset:")):
                    continue
                artifact_path = edge.from_id.split(":", 1)[1]
                artifact = artifact_index.get(artifact_path)
                if artifact is not None:
                    artifacts[artifact.artifact_path] = artifact
            for claim in source_claims.get(source.source_key, []):
                for edge in _outgoing(self.claim_node_id(claim.claim_key), "supports"):
                    if not edge.to_id.startswith(("artifact:", "dataset:")):
                        continue
                    artifact_path = edge.to_id.split(":", 1)[1]
                    artifact = artifact_index.get(artifact_path)
                    if artifact is not None:
                        artifacts[artifact.artifact_path] = artifact
            source_artifacts[source.source_key] = list(artifacts.values())

        claim_artifacts: dict[str, list[ArtifactLineageRecord]] = {}
        for claim in indexes.claims:
            artifacts = []
            for edge in _outgoing(self.claim_node_id(claim.claim_key), "supports"):
                if not edge.to_id.startswith(("artifact:", "dataset:")):
                    continue
                artifact_path = edge.to_id.split(":", 1)[1]
                artifact = artifact_index.get(artifact_path)
                if artifact is not None:
                    artifacts.append(artifact)
            claim_artifacts[claim.claim_key] = artifacts

        artifact_sources: dict[str, list[SourceRecord]] = {}
        artifact_claims: dict[str, list[ClaimRecord]] = {}
        for artifact in indexes.artifact_lineage:
            artifact_id = artifact_node_ids[artifact.artifact_path]
            sources = []
            claims = []
            for edge in _outgoing(artifact_id, "derived_from"):
                source_key = edge.to_id.removeprefix("source:")
                source = source_index.get(source_key)
                if source is not None:
                    sources.append(source)
            for edge in _incoming(artifact_id, "supports"):
                claim_key = edge.from_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None:
                    claims.append(claim)
            artifact_sources[artifact.artifact_path] = sources
            artifact_claims[artifact.artifact_path] = claims

        chunk_claims: dict[str, list[ClaimRecord]] = {}
        for chunk in indexes.evidence_chunks:
            claims = []
            for edge in _outgoing(self.chunk_node_id(chunk.chunk_key), "supports"):
                claim_key = edge.to_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None:
                    claims.append(claim)
            chunk_claims[chunk.chunk_key] = claims

        source_freshness_filter = set(source_freshness or [])
        claim_status_filter = set(claim_statuses or [])
        artifact_type_filter = set(artifact_types or [])
        date_from_dt = _parse_timestamp(date_from)
        date_to_dt = _parse_timestamp(date_to)

        def _within_window(timestamp) -> bool:
            if timestamp is None:
                return True
            if date_from_dt is not None and timestamp < date_from_dt:
                return False
            if date_to_dt is not None and timestamp > date_to_dt:
                return False
            return True

        def _source_timestamp(source: SourceRecord):
            return (
                _parse_timestamp(source.acquired_at)
                or _parse_timestamp(source.retrieved_at)
                or _parse_timestamp(source.updated_at)
                or _parse_timestamp(source.created_at)
            )

        def _claim_timestamp(claim: ClaimRecord):
            return _parse_timestamp(claim.updated_at) or _parse_timestamp(claim.created_at)

        def _artifact_timestamp(artifact: ArtifactLineageRecord):
            return (
                _parse_timestamp(artifact.generated_at)
                or _parse_timestamp(artifact.updated_at)
                or _parse_timestamp(artifact.created_at)
            )

        def _chunk_timestamp(chunk: EvidenceChunkRecord):
            return _parse_timestamp(chunk.updated_at) or _parse_timestamp(chunk.created_at)

        def _source_excluded(source: SourceRecord) -> bool:
            if source_freshness_filter and source.freshness_status not in source_freshness_filter:
                return True
            if not _within_window(_source_timestamp(source)):
                return True
            if not include_stale and source.freshness_status == "stale":
                return True
            if not include_blocked and source.quality_status in {"blocked", "rejected"}:
                return True
            return False

        def _claim_excluded(claim: ClaimRecord) -> bool:
            if claim_status_filter and claim.status not in claim_status_filter:
                return True
            if not _within_window(_claim_timestamp(claim)):
                return True
            if not include_stale and claim.status in {"stale", "conflicted"}:
                return True
            if any(_source_excluded(source_index[source_key]) for source_key in claim.source_keys if source_key in source_index):
                return True
            return False

        def _artifact_excluded(artifact: ArtifactLineageRecord) -> bool:
            if artifact_type_filter and artifact.artifact_type not in artifact_type_filter:
                return True
            if not _within_window(_artifact_timestamp(artifact)):
                return True
            if not include_stale and artifact.promotion_state == "stale":
                return True
            if not include_blocked and artifact.promotion_state == "blocked":
                return True
            if any(_source_excluded(source) for source in artifact_sources.get(artifact.artifact_path, [])):
                return True
            if any(_claim_excluded(claim) for claim in artifact_claims.get(artifact.artifact_path, [])):
                return True
            return False

        def _chunk_excluded(chunk: EvidenceChunkRecord) -> bool:
            source = source_index.get(chunk.source_key)
            if not _within_window(_chunk_timestamp(chunk)):
                return True
            if source is not None and _source_excluded(source):
                return True
            if not include_stale and chunk.status == "stale":
                return True
            if not include_blocked and chunk.status == "blocked":
                return True
            return False

        def _chunk_is_explicit(chunk: EvidenceChunkRecord) -> bool:
            return not _chunk_excluded(chunk) and any(
                _claim_is_explicit(claim)
                for claim in chunk_claims.get(chunk.chunk_key, [])
            )

        def _claim_is_explicit(claim: ClaimRecord) -> bool:
            return (
                claim.status == "supported"
                and claim.evidence_kind != "semantic_suggestion"
                and not _claim_excluded(claim)
                and bool(claim.evidence_paths or claim.source_keys or claim.evidence_chunk_keys)
            )

        def _source_is_explicit(source: SourceRecord) -> bool:
            return not _source_excluded(source) and (
                any(
                    _claim_is_explicit(claim)
                    for claim in source_claims.get(source.source_key, [])
                )
                or any(
                    not _artifact_excluded(artifact)
                    for artifact in source_artifacts.get(source.source_key, [])
                )
            )

        def _artifact_is_explicit(artifact: ArtifactLineageRecord) -> bool:
            return not _artifact_excluded(artifact) and (
                any(_claim_is_explicit(claim) for claim in artifact_claims.get(artifact.artifact_path, []))
                or any(not _source_excluded(source) for source in artifact_sources.get(artifact.artifact_path, []))
            )

        def _claim_support_path(claim: ClaimRecord) -> list[str] | None:
            claim_id = self.claim_node_id(claim.claim_key)
            for edge in _incoming(claim_id, "supports"):
                if edge.from_id.startswith("chunk:"):
                    chunk_key = edge.from_id.removeprefix("chunk:")
                    chunk = chunk_index.get(chunk_key)
                    if chunk is not None and not _chunk_excluded(chunk):
                        return [edge.from_id, claim_id]
                if edge.from_id.startswith("source:"):
                    source_key = edge.from_id.removeprefix("source:")
                    source = source_index.get(source_key)
                    if source is not None and not _source_excluded(source):
                        return [edge.from_id, claim_id]
            return None

        def _artifact_support_path(artifact: ArtifactLineageRecord) -> list[str] | None:
            artifact_id = artifact_node_ids[artifact.artifact_path]
            for edge in _incoming(artifact_id, "supports"):
                claim_key = edge.from_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None and _claim_is_explicit(claim):
                    claim_path = _claim_support_path(claim)
                    return [*claim_path, artifact_id] if claim_path else [edge.from_id, artifact_id]
            for edge in _outgoing(artifact_id, "derived_from"):
                source_key = edge.to_id.removeprefix("source:")
                source = source_index.get(source_key)
                if source is not None and not _source_excluded(source):
                    return [artifact_id, edge.to_id]
            return None

        def _source_support_path(source: SourceRecord) -> list[str] | None:
            source_id = self.source_node_id(source.source_key)
            for edge in _outgoing(source_id, "supports"):
                claim_key = edge.to_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None and _claim_is_explicit(claim):
                    return [source_id, edge.to_id]
            for edge in _incoming(source_id, "derived_from"):
                artifact_path = edge.from_id.split(":", 1)[1]
                artifact = artifact_index.get(artifact_path)
                if artifact is not None and not _artifact_excluded(artifact):
                    return [edge.from_id, source_id]
            return None

        def _chunk_support_path(chunk: EvidenceChunkRecord) -> list[str] | None:
            chunk_id = self.chunk_node_id(chunk.chunk_key)
            for edge in _outgoing(chunk_id, "supports"):
                claim_key = edge.to_id.removeprefix("claim:")
                claim = claim_index.get(claim_key)
                if claim is not None and _claim_is_explicit(claim):
                    return [chunk_id, edge.to_id]
            return None

        def _source_text(source: SourceRecord) -> str:
            provenance_bits = [
                str(source.provenance.get(key))
                for key in ("config_path", "path", "url", "storage_key", "response_path")
                if source.provenance.get(key)
            ]
            return " ".join(
                [
                    source.source_key,
                    source.title,
                    source.source_type,
                    source.url_or_path,
                    source.origin or "",
                    source.notes or "",
                    source.quality_notes or "",
                    " ".join(provenance_bits),
                ]
            )

        def _claim_text(claim: ClaimRecord) -> str:
            return " ".join(
                [
                    claim.claim_key,
                    claim.claim_text,
                    claim.artifact_path or "",
                    " ".join(claim.evidence_paths),
                    " ".join(claim.evidence_chunk_keys),
                    " ".join(claim.caveats),
                    " ".join(claim.open_questions),
                    " ".join(claim.source_keys),
                ]
            )

        def _artifact_text(artifact: ArtifactLineageRecord) -> str:
            return " ".join(
                [
                    artifact.artifact_path,
                    artifact.title,
                    artifact.artifact_type,
                    " ".join(artifact.inputs),
                    " ".join(artifact.scripts),
                    " ".join(artifact.sources),
                    " ".join(artifact.claims),
                ]
            )

        def _chunk_text(chunk: EvidenceChunkRecord) -> str:
            return " ".join(
                [
                    chunk.chunk_key,
                    chunk.text,
                    str(chunk.metadata.get("source_title") or ""),
                    str(chunk.metadata.get("source_type") or ""),
                    str(chunk.metadata.get("url_or_path") or ""),
                ]
            )

        query_embedding = _hash_embedding(q)
        scored_candidates: list[dict[str, Any]] = []

        for source in indexes.sources:
            if _source_excluded(source):
                continue
            source_text = _source_text(source)
            score = _semantic_score(q, source_text, query_embedding=query_embedding)
            if score < MIN_SEMANTIC_SCORE:
                continue
            scored_candidates.append(
                {
                    "recordType": "source",
                    "recordKey": source.source_key,
                    "score": score,
                    "record": source,
                }
            )

        for claim in indexes.claims:
            if _claim_excluded(claim):
                continue
            claim_text = _claim_text(claim)
            score = _semantic_score(q, claim_text, query_embedding=query_embedding)
            if score < MIN_SEMANTIC_SCORE:
                continue
            scored_candidates.append(
                {
                    "recordType": "claim",
                    "recordKey": claim.claim_key,
                    "score": score,
                    "record": claim,
                }
            )

        for artifact in indexes.artifact_lineage:
            if _artifact_excluded(artifact):
                continue
            artifact_text = _artifact_text(artifact)
            score = _semantic_score(q, artifact_text, query_embedding=query_embedding)
            if score < MIN_SEMANTIC_SCORE:
                continue
            scored_candidates.append(
                {
                    "recordType": "artifact",
                    "recordKey": artifact.artifact_path,
                    "score": score,
                    "record": artifact,
                }
            )

        for chunk in indexes.evidence_chunks:
            if _chunk_excluded(chunk):
                continue
            chunk_text = _chunk_text(chunk)
            chunk_embedding = chunk.embedding if chunk.embedding else _hash_embedding(chunk_text)
            score = _semantic_score(q, chunk_text, query_embedding=query_embedding, record_embedding=chunk_embedding)
            if score < MIN_SEMANTIC_SCORE:
                continue
            scored_candidates.append(
                {
                    "recordType": "chunk",
                    "recordKey": chunk.chunk_key,
                    "score": score,
                    "record": chunk,
                }
            )

        scored_candidates.sort(key=lambda item: (item["score"], item["recordType"], item["recordKey"]), reverse=True)

        results_by_key: dict[tuple[str, str], dict[str, Any]] = {}

        def _store_result(
            *,
            result_type: Literal["explicit_evidence", "semantic_suggestion"],
            record_type: Literal["source", "claim", "artifact", "chunk"],
            record_key: str,
            title: str,
            text: str,
            score: float,
            reason: str,
            source_keys_value: list[str],
            claim_keys_value: list[str],
            metadata: dict[str, Any],
            graph_path: list[str] | None = None,
            trust_basis: str | None = None,
            matched_node: str | None = None,
            expanded_from: str | None = None,
        ) -> None:
            key = (record_type, record_key)
            payload = {
                "resultType": result_type,
                "recordType": record_type,
                "recordKey": record_key,
                "title": title,
                "text": text,
                "score": round(score, 4),
                "reason": reason,
                "sourceKeys": sorted(set(source_keys_value)),
                "claimKeys": sorted(set(claim_keys_value)),
                **metadata,
            }
            if graph_path is not None:
                payload["graphPath"] = graph_path
            if trust_basis is not None:
                payload["trustBasis"] = trust_basis
            if matched_node is not None:
                payload["matchedNode"] = matched_node
            if expanded_from is not None:
                payload["expandedFrom"] = expanded_from
            existing = results_by_key.get(key)
            if existing is None:
                results_by_key[key] = payload
                return
            if existing["resultType"] == "semantic_suggestion" and result_type == "explicit_evidence":
                results_by_key[key] = payload
                return
            if score > existing["score"]:
                results_by_key[key] = payload

        for candidate in scored_candidates[: max(limit * 3, limit)]:
            record_type = candidate["recordType"]
            score = float(candidate["score"])
            if record_type == "source":
                source = candidate["record"]
                source_node = self.source_node_id(source.source_key)
                source_graph_path = _source_support_path(source) or [source_node]
                if not expand_explicit:
                    _store_result(
                        result_type="explicit_evidence" if _source_is_explicit(source) else "semantic_suggestion",
                        record_type="source",
                        record_key=source.source_key,
                        title=source.title,
                        text=source.notes or source.quality_notes or source.url_or_path,
                        score=score + (0.1 if _source_is_explicit(source) else 0),
                        reason="Direct semantic retrieval result." if _source_is_explicit(source) else "Semantically relevant source candidate.",
                        source_keys_value=[source.source_key],
                        claim_keys_value=[claim.claim_key for claim in source_claims.get(source.source_key, []) if _claim_is_explicit(claim)],
                        metadata={
                            "freshnessStatus": source.freshness_status,
                            "qualityStatus": source.quality_status,
                            "artifactPaths": [artifact.artifact_path for artifact in source_artifacts.get(source.source_key, []) if not _artifact_excluded(artifact)],
                        },
                        graph_path=source_graph_path,
                        trust_basis="graph_explicit_support" if _source_is_explicit(source) else "semantic_match_only",
                        matched_node=source_node,
                    )
                    continue
                if _source_is_explicit(source):
                    _store_result(
                        result_type="explicit_evidence",
                        record_type="source",
                        record_key=source.source_key,
                        title=source.title,
                        text=source.notes or source.quality_notes or source.url_or_path,
                        score=score + 0.25,
                        reason="Directly linked source with supported claim evidence.",
                        source_keys_value=[source.source_key],
                        claim_keys_value=[claim.claim_key for claim in source_claims.get(source.source_key, []) if _claim_is_explicit(claim)],
                        metadata={
                            "freshnessStatus": source.freshness_status,
                            "qualityStatus": source.quality_status,
                            "artifactPaths": [artifact.artifact_path for artifact in source_artifacts.get(source.source_key, []) if not _artifact_excluded(artifact)],
                        },
                        graph_path=source_graph_path,
                        trust_basis="matched source with persisted explicit support path",
                        matched_node=source_node,
                    )
                    for claim in source_claims.get(source.source_key, []):
                        if not _claim_is_explicit(claim):
                            continue
                        claim_path = [source_node, self.claim_node_id(claim.claim_key)]
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="claim",
                            record_key=claim.claim_key,
                            title=claim.claim_key,
                            text=claim.claim_text,
                            score=score + 0.2,
                            reason="Claim is explicitly supported by a matched source.",
                            source_keys_value=list(claim.source_keys),
                            claim_keys_value=[claim.claim_key],
                            metadata={
                                "claimStatus": claim.status,
                                "evidenceKind": claim.evidence_kind,
                                "artifactPath": claim.artifact_path,
                                "evidencePaths": list(claim.evidence_paths),
                            },
                            graph_path=claim_path,
                            trust_basis="semantic match expanded through persisted source->claim edge",
                            matched_node=source_node,
                            expanded_from=source_node,
                        )
                    for artifact in source_artifacts.get(source.source_key, []):
                        if not _artifact_is_explicit(artifact):
                            continue
                        artifact_path = _artifact_support_path(artifact) or [artifact_node_ids[artifact.artifact_path], source_node]
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="artifact",
                            record_key=artifact.artifact_path,
                            title=artifact.title,
                            text=artifact.artifact_path,
                            score=score + 0.15,
                            reason="Artifact has explicit lineage to a matched source.",
                            source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                            claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                            metadata={
                                "artifactPath": artifact.artifact_path,
                                "artifactType": artifact.artifact_type,
                                "promotionState": artifact.promotion_state,
                            },
                            graph_path=artifact_path,
                            trust_basis="semantic match expanded through persisted graph lineage",
                            matched_node=source_node,
                            expanded_from=source_node,
                        )
                else:
                    _store_result(
                        result_type="semantic_suggestion",
                        record_type="source",
                        record_key=source.source_key,
                        title=source.title,
                        text=source.notes or source.quality_notes or source.url_or_path,
                        score=score,
                        reason="Semantically relevant source candidate that is not attached as explicit evidence.",
                        source_keys_value=[source.source_key],
                        claim_keys_value=[],
                        metadata={
                            "freshnessStatus": source.freshness_status,
                            "qualityStatus": source.quality_status,
                            "artifactPaths": [artifact.artifact_path for artifact in source_artifacts.get(source.source_key, []) if not _artifact_excluded(artifact)],
                        },
                        graph_path=[source_node],
                        trust_basis="semantic_match_only",
                        matched_node=source_node,
                    )
            elif record_type == "claim":
                claim = candidate["record"]
                claim_node = self.claim_node_id(claim.claim_key)
                claim_graph_path = _claim_support_path(claim) or [claim_node]
                if not expand_explicit:
                    _store_result(
                        result_type="explicit_evidence" if _claim_is_explicit(claim) else "semantic_suggestion",
                        record_type="claim",
                        record_key=claim.claim_key,
                        title=claim.claim_key,
                        text=claim.claim_text,
                        score=score + (0.1 if _claim_is_explicit(claim) else 0),
                        reason="Direct semantic retrieval result." if _claim_is_explicit(claim) else "Semantically relevant claim candidate that still needs explicit evidence.",
                        source_keys_value=list(claim.source_keys),
                        claim_keys_value=[claim.claim_key],
                        metadata={
                            "claimStatus": claim.status,
                            "evidenceKind": claim.evidence_kind,
                            "artifactPath": claim.artifact_path,
                            "evidencePaths": list(claim.evidence_paths),
                            "evidenceChunkKeys": list(claim.evidence_chunk_keys),
                        },
                        graph_path=claim_graph_path,
                        trust_basis="graph_explicit_support" if _claim_is_explicit(claim) else "semantic_match_only",
                        matched_node=claim_node,
                    )
                    continue
                if _claim_is_explicit(claim):
                    _store_result(
                        result_type="explicit_evidence",
                        record_type="claim",
                        record_key=claim.claim_key,
                        title=claim.claim_key,
                        text=claim.claim_text,
                        score=score + 0.25,
                        reason="Explicitly supported claim matched the query.",
                        source_keys_value=list(claim.source_keys),
                        claim_keys_value=[claim.claim_key],
                        metadata={
                            "claimStatus": claim.status,
                            "evidenceKind": claim.evidence_kind,
                            "artifactPath": claim.artifact_path,
                            "evidencePaths": list(claim.evidence_paths),
                        },
                        graph_path=claim_graph_path,
                        trust_basis="matched supported claim with persisted evidence edge",
                        matched_node=claim_node,
                    )
                    for source_key in claim.source_keys:
                        source = source_index.get(source_key)
                        if source is None or _source_excluded(source):
                            continue
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="source",
                            record_key=source.source_key,
                            title=source.title,
                            text=source.notes or source.quality_notes or source.url_or_path,
                            score=score + 0.15,
                            reason="Source is explicitly attached to a matched supported claim.",
                            source_keys_value=[source.source_key],
                            claim_keys_value=[claim.claim_key],
                            metadata={
                                "freshnessStatus": source.freshness_status,
                                "qualityStatus": source.quality_status,
                                "artifactPaths": [artifact.artifact_path for artifact in source_artifacts.get(source.source_key, []) if not _artifact_excluded(artifact)],
                            },
                            graph_path=[self.source_node_id(source.source_key), claim_node],
                            trust_basis="semantic match expanded through persisted source->claim edge",
                            matched_node=claim_node,
                            expanded_from=claim_node,
                        )
                    for artifact in claim_artifacts.get(claim.claim_key, []):
                        if _artifact_excluded(artifact):
                            continue
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="artifact",
                            record_key=artifact.artifact_path,
                            title=artifact.title,
                            text=artifact.artifact_path,
                            score=score + 0.1,
                            reason="Artifact explicitly depends on a matched supported claim.",
                            source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                            claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                            metadata={
                                "artifactPath": artifact.artifact_path,
                                "artifactType": artifact.artifact_type,
                                "promotionState": artifact.promotion_state,
                            },
                            graph_path=[*claim_graph_path, artifact_node_ids[artifact.artifact_path]],
                            trust_basis="semantic match expanded through persisted claim->artifact edge",
                            matched_node=claim_node,
                            expanded_from=claim_node,
                        )
                else:
                    _store_result(
                        result_type="semantic_suggestion",
                        record_type="claim",
                        record_key=claim.claim_key,
                        title=claim.claim_key,
                        text=claim.claim_text,
                        score=score,
                        reason="Semantically relevant claim candidate that still needs explicit evidence.",
                        source_keys_value=list(claim.source_keys),
                        claim_keys_value=[claim.claim_key],
                        metadata={
                            "claimStatus": claim.status,
                            "evidenceKind": claim.evidence_kind,
                            "artifactPath": claim.artifact_path,
                            "evidencePaths": list(claim.evidence_paths),
                        },
                        graph_path=[claim_node],
                        trust_basis="semantic_match_only",
                        matched_node=claim_node,
                    )
            elif record_type == "artifact":
                artifact = candidate["record"]
                artifact_node = artifact_node_ids[artifact.artifact_path]
                artifact_graph_path = _artifact_support_path(artifact) or [artifact_node]
                if not expand_explicit:
                    _store_result(
                        result_type="explicit_evidence" if _artifact_is_explicit(artifact) else "semantic_suggestion",
                        record_type="artifact",
                        record_key=artifact.artifact_path,
                        title=artifact.title,
                        text=artifact.artifact_path,
                        score=score + (0.1 if _artifact_is_explicit(artifact) else 0),
                        reason="Direct semantic retrieval result." if _artifact_is_explicit(artifact) else "Semantically relevant artifact candidate without explicit trusted evidence.",
                        source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                        claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                        metadata={
                            "artifactPath": artifact.artifact_path,
                            "artifactType": artifact.artifact_type,
                            "promotionState": artifact.promotion_state,
                        },
                        graph_path=artifact_graph_path,
                        trust_basis="graph_explicit_support" if _artifact_is_explicit(artifact) else "semantic_match_only",
                        matched_node=artifact_node,
                    )
                    continue
                if _artifact_is_explicit(artifact):
                    _store_result(
                        result_type="explicit_evidence",
                        record_type="artifact",
                        record_key=artifact.artifact_path,
                        title=artifact.title,
                        text=artifact.artifact_path,
                        score=score + 0.25,
                        reason="Artifact lineage explicitly connects to supported evidence.",
                        source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                        claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                        metadata={
                            "artifactPath": artifact.artifact_path,
                            "artifactType": artifact.artifact_type,
                            "promotionState": artifact.promotion_state,
                        },
                        graph_path=artifact_graph_path,
                        trust_basis="matched artifact with persisted lineage path",
                        matched_node=artifact_node,
                    )
                    for claim in artifact_claims.get(artifact.artifact_path, []):
                        if not _claim_is_explicit(claim):
                            continue
                        claim_path = _claim_support_path(claim) or [self.claim_node_id(claim.claim_key)]
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="claim",
                            record_key=claim.claim_key,
                            title=claim.claim_key,
                            text=claim.claim_text,
                            score=score + 0.15,
                            reason="Matched artifact is backed by an explicitly supported claim.",
                            source_keys_value=list(claim.source_keys),
                            claim_keys_value=[claim.claim_key],
                            metadata={
                                "claimStatus": claim.status,
                                "evidenceKind": claim.evidence_kind,
                                "artifactPath": claim.artifact_path,
                                "evidencePaths": list(claim.evidence_paths),
                            },
                            graph_path=[*claim_path, artifact_node],
                            trust_basis="semantic match expanded through persisted artifact claim support",
                            matched_node=artifact_node,
                            expanded_from=artifact_node,
                        )
                    for source in artifact_sources.get(artifact.artifact_path, []):
                        if not _source_is_explicit(source):
                            continue
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="source",
                            record_key=source.source_key,
                            title=source.title,
                            text=source.notes or source.quality_notes or source.url_or_path,
                            score=score + 0.1,
                            reason="Matched artifact preserves explicit source lineage.",
                            source_keys_value=[source.source_key],
                            claim_keys_value=[claim.claim_key for claim in source_claims.get(source.source_key, []) if _claim_is_explicit(claim)],
                            metadata={
                                "freshnessStatus": source.freshness_status,
                                "qualityStatus": source.quality_status,
                                "artifactPaths": [artifact.artifact_path for artifact in source_artifacts.get(source.source_key, []) if not _artifact_excluded(artifact)],
                            },
                            graph_path=[artifact_node, self.source_node_id(source.source_key)],
                            trust_basis="semantic match expanded through persisted artifact->source lineage",
                            matched_node=artifact_node,
                            expanded_from=artifact_node,
                        )
                else:
                    _store_result(
                        result_type="semantic_suggestion",
                        record_type="artifact",
                        record_key=artifact.artifact_path,
                        title=artifact.title,
                        text=artifact.artifact_path,
                        score=score,
                        reason="Semantically relevant artifact candidate without explicit trusted evidence.",
                        source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                        claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                        metadata={
                            "artifactPath": artifact.artifact_path,
                            "artifactType": artifact.artifact_type,
                            "promotionState": artifact.promotion_state,
                        },
                        graph_path=[artifact_node],
                        trust_basis="semantic_match_only",
                        matched_node=artifact_node,
                    )
            else:
                chunk = candidate["record"]
                source = source_index.get(chunk.source_key)
                chunk_node = self.chunk_node_id(chunk.chunk_key)
                chunk_graph_path = _chunk_support_path(chunk) or [chunk_node]
                if not expand_explicit:
                    _store_result(
                        result_type="explicit_evidence" if _chunk_is_explicit(chunk) else "semantic_suggestion",
                        record_type="chunk",
                        record_key=chunk.chunk_key,
                        title=f"Chunk from {source.title if source else chunk.source_key}",
                        text=chunk.text,
                        score=score + (0.1 if _chunk_is_explicit(chunk) else 0),
                        reason="Direct semantic retrieval result." if _chunk_is_explicit(chunk) else "Semantically relevant source chunk candidate.",
                        source_keys_value=[chunk.source_key],
                        claim_keys_value=[claim.claim_key for claim in chunk_claims.get(chunk.chunk_key, []) if _claim_is_explicit(claim)],
                        metadata={
                            "chunkKey": chunk.chunk_key,
                            "chunkStatus": chunk.status,
                            "chunkType": chunk.chunk_type,
                            "sourceMetadata": chunk.metadata,
                        },
                        graph_path=chunk_graph_path,
                        trust_basis="graph_explicit_support" if _chunk_is_explicit(chunk) else "semantic_match_only",
                        matched_node=chunk_node,
                    )
                    continue
                if _chunk_is_explicit(chunk):
                    _store_result(
                        result_type="explicit_evidence",
                        record_type="chunk",
                        record_key=chunk.chunk_key,
                        title=f"Chunk from {source.title if source else chunk.source_key}",
                        text=chunk.text,
                        score=score + 0.2,
                        reason="Source chunk is explicitly attached to a supported claim.",
                        source_keys_value=[chunk.source_key],
                        claim_keys_value=[claim.claim_key for claim in chunk_claims.get(chunk.chunk_key, []) if _claim_is_explicit(claim)],
                        metadata={
                            "chunkKey": chunk.chunk_key,
                            "chunkStatus": chunk.status,
                            "chunkType": chunk.chunk_type,
                            "sourceMetadata": chunk.metadata,
                        },
                        graph_path=chunk_graph_path,
                        trust_basis="matched chunk with persisted chunk->claim support edge",
                        matched_node=chunk_node,
                    )
                    for claim in chunk_claims.get(chunk.chunk_key, []):
                        if not _claim_is_explicit(claim):
                            continue
                        claim_path = [chunk_node, self.claim_node_id(claim.claim_key)]
                        _store_result(
                            result_type="explicit_evidence",
                            record_type="claim",
                            record_key=claim.claim_key,
                            title=claim.claim_key,
                            text=claim.claim_text,
                            score=score + 0.15,
                            reason="Matched chunk is explicitly attached to a supported claim.",
                            source_keys_value=list(claim.source_keys),
                            claim_keys_value=[claim.claim_key],
                            metadata={
                                "claimStatus": claim.status,
                                "evidenceKind": claim.evidence_kind,
                                "artifactPath": claim.artifact_path,
                                "evidencePaths": list(claim.evidence_paths),
                                "evidenceChunkKeys": list(claim.evidence_chunk_keys),
                            },
                            graph_path=claim_path,
                            trust_basis="semantic match expanded through persisted chunk->claim edge",
                            matched_node=chunk_node,
                            expanded_from=chunk_node,
                        )
                        for artifact in claim_artifacts.get(claim.claim_key, []):
                            if _artifact_excluded(artifact):
                                continue
                            _store_result(
                                result_type="explicit_evidence",
                                record_type="artifact",
                                record_key=artifact.artifact_path,
                                title=artifact.title,
                                text=artifact.artifact_path,
                                score=score + 0.1,
                                reason="Matched chunk supports a claim used by this artifact.",
                                source_keys_value=[_normalize_reference_key(reference) for reference in artifact.sources],
                                claim_keys_value=[_normalize_reference_key(reference) for reference in artifact.claims],
                                metadata={
                                    "artifactPath": artifact.artifact_path,
                                    "artifactType": artifact.artifact_type,
                                    "promotionState": artifact.promotion_state,
                                },
                                graph_path=[*claim_path, artifact_node_ids[artifact.artifact_path]],
                                trust_basis="semantic match expanded through persisted chunk->claim->artifact path",
                                matched_node=chunk_node,
                                expanded_from=chunk_node,
                            )
                else:
                    _store_result(
                        result_type="semantic_suggestion",
                        record_type="chunk",
                        record_key=chunk.chunk_key,
                        title=f"Chunk from {source.title if source else chunk.source_key}",
                        text=chunk.text,
                        score=score,
                        reason="Semantically relevant source chunk; explicit evidence still requires attachment to a claim.",
                        source_keys_value=[chunk.source_key],
                        claim_keys_value=[],
                        metadata={
                            "chunkKey": chunk.chunk_key,
                            "chunkStatus": chunk.status,
                            "chunkType": chunk.chunk_type,
                            "sourceMetadata": chunk.metadata,
                        },
                        graph_path=[chunk_node],
                        trust_basis="semantic_match_only",
                        matched_node=chunk_node,
                    )

        results = sorted(
            results_by_key.values(),
            key=lambda item: (
                1 if item["resultType"] == "explicit_evidence" else 0,
                item["score"],
                item["recordType"],
                item["recordKey"],
            ),
            reverse=True,
        )[:limit]

        explicit_count = sum(1 for item in results if item["resultType"] == "explicit_evidence")
        semantic_count = sum(1 for item in results if item["resultType"] == "semantic_suggestion")
        return {
            "query": query,
            "results": results,
            "summary": {
                "resultCount": len(results),
                "explicitEvidenceCount": explicit_count,
                "semanticSuggestionCount": semantic_count,
            },
                "filters": {
                    "artifactTypes": artifact_types or [],
                    "claimStatuses": claim_statuses or [],
                    "sourceFreshness": source_freshness or [],
                    "dateFrom": date_from,
                    "dateTo": date_to,
                    "includeStale": include_stale,
                    "includeBlocked": include_blocked,
                    "expandExplicit": expand_explicit,
                },
            }

    def clear_artifact_stale(
        self,
        artifact_paths: list[str],
        *,
        promotion_state: PromotionState | None = None,
    ) -> list[ArtifactLineageRecord]:
        changed: list[ArtifactLineageRecord] = []
        wanted = set(artifact_paths)
        if not wanted:
            return changed
        records = self.load_artifact_lineage()
        for idx, record in enumerate(records):
            if record.artifact_path not in wanted:
                continue
            updated = record.model_copy(
                update={
                    "promotion_state": promotion_state or ("partially_verified" if record.promotion_state == "stale" else record.promotion_state),
                    "stale_reasons": [],
                    "stale_marked_at": None,
                }
            )
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_artifact_lineage(records)
        return changed

    def _set_chunk_status_for_source(
        self,
        source_key: str,
        *,
        status: Literal["active", "stale", "blocked"],
    ) -> list[EvidenceChunkRecord]:
        changed: list[EvidenceChunkRecord] = []
        records = self.load_evidence_chunks()
        for idx, record in enumerate(records):
            if record.source_key != source_key:
                continue
            updated = record.model_copy(update={"status": status})
            updated = self._normalize_timestamps(updated, preserve_created_at=record.created_at)
            records[idx] = updated
            changed.append(updated)
        if changed:
            self.write_evidence_chunks(records)
        return changed

    def _resolve_source_text(self, source: SourceRecord) -> str:
        provenance = source.provenance or {}
        for key in ("text", "text_content", "content", "extracted_text", "body", "snippet"):
            value = provenance.get(key)
            if isinstance(value, str) and value.strip():
                return value
        config_path = provenance.get("config_path")
        url_or_path = source.url_or_path
        candidate_paths: list[Path] = []
        if isinstance(url_or_path, str) and url_or_path:
            candidate_paths.append((self.project_root / url_or_path).resolve())
            candidate_paths.append(Path(url_or_path).expanduser())
        if isinstance(config_path, str) and config_path:
            candidate_paths.append((self.project_root / config_path).resolve())
        for candidate in candidate_paths:
            try:
                if candidate.is_file():
                    suffix = candidate.suffix.lower()
                    if suffix in {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}:
                        return candidate.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
        return ""

    def _chunk_text(
        self,
        text: str,
        *,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[str]:
        normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
        if not normalized:
            return []
        paragraphs = [item.strip() for item in normalized.split("\n\n") if item.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= chunk_size:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(paragraph) <= chunk_size:
                current = paragraph
                continue
            start = 0
            step = max(1, chunk_size - max(0, chunk_overlap))
            while start < len(paragraph):
                end = min(len(paragraph), start + chunk_size)
                piece = paragraph[start:end].strip()
                if piece:
                    chunks.append(piece)
                if end >= len(paragraph):
                    break
                start += step
            current = ""
        if current:
            chunks.append(current)
        return chunks

    def _upsert_by_key(
        self,
        load_fn: Any,
        write_fn: Any,
        model_cls: type[BaseModel],
        key_field: str,
        record: BaseModel | dict[str, Any],
    ) -> Any:
        stored = self._normalize_timestamps(model_cls.model_validate(record))
        key = getattr(stored, key_field)
        records = load_fn()
        index = {getattr(item, key_field): item for item in records}
        existing = index.get(key)
        if existing and stored.created_at is None:
            stored.created_at = existing.created_at
        merged = self._normalize_timestamps(stored, preserve_created_at=existing.created_at if existing else None)
        index[key] = merged
        write_fn(list(index.values()))
        return merged

    def _load_records(self, path: Path, model_cls: type[BaseModel]) -> list[Any]:
        self.ensure_files_exist()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(raw, list):
            raise ValueError(f"{path} must contain a JSON array")
        normalized_raw = raw
        if model_cls is VerificationRunRecord:
            normalized_raw = [
                _normalize_legacy_verification_run_record(item) if isinstance(item, dict) else item
                for item in raw
            ]
        elif model_cls is ClaimRecord:
            normalized_raw = [
                _normalize_legacy_claim_record(item) if isinstance(item, dict) else item
                for item in raw
            ]
        try:
            return [model_cls.model_validate(item) for item in normalized_raw]
        except ValidationError as exc:
            raise ValueError(f"Invalid integrity records in {path}: {exc}") from exc

    def _candidate_key(self, prefix: str, value: str) -> str:
        normalized = "-".join(_tokenize_text(value)[:8]) or prefix
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}:{normalized}-{digest}"

    def _record_key(self, prefix: str, value: str) -> str:
        normalized = "-".join(_tokenize_text(value)[:8]) or prefix
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}-{normalized}-{digest}"

    def _default_claim_status(
        self,
        evidence_paths: list[str],
        source_keys: list[str],
        evidence_chunk_keys: list[str],
        evidence_kind: EvidenceKind | None,
    ) -> ClaimStatus:
        has_evidence = bool(evidence_paths or source_keys or evidence_chunk_keys)
        if has_evidence and evidence_kind != "semantic_suggestion":
            return "supported"
        return "needs_evidence"

    def _source_candidate_key_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for source in self.load_sources():
            candidate_key = str(source.provenance.get("sourceCandidateKey") or "")
            if candidate_key:
                mapping[candidate_key] = source.source_key
        return mapping

    def _resolve_source_keys_for_claim_candidate(self, candidate: ClaimCandidateRecord) -> list[str]:
        candidate_to_source = self._source_candidate_key_map()
        resolved = [
            candidate_to_source[source_candidate_key]
            for source_candidate_key in candidate.source_candidate_keys
            if source_candidate_key in candidate_to_source
        ]
        return sorted(set(resolved))

    def _title_from_url(self, url: str) -> str:
        trimmed = url.split("://", 1)[-1]
        return trimmed[:120]

    def _estimate_relevance(self, text: str) -> float:
        lowered = text.lower()
        score = 0.2
        for token in ("evidence", "impact", "effect", "result", "finding", "source", "dataset", "study"):
            if token in lowered:
                score += 0.08
        return min(score, 1.0)

    def _first_matching_line(self, text: str, needle: str) -> str | None:
        for line in text.splitlines():
            if needle in line:
                return line.strip()[:400]
        return None

    def _extract_claim_candidate_texts(self, text: str) -> list[tuple[str, str]]:
        claim_candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        trigger_phrases = (
            "we find",
            "evidence suggests",
            "results suggest",
            "this suggests",
            "this indicates",
            "appears to",
            "is associated with",
            "remains incomplete",
            "should not be presented",
        )
        for raw_line in text.splitlines():
            line = raw_line.strip().lstrip("-*0123456789. ").strip()
            if len(line) < 35 or len(line) > 400:
                continue
            lowered = line.lower()
            candidate_text: str | None = None
            if lowered.startswith(("claim:", "finding:", "hypothesis:", "question:")):
                candidate_text = line.split(":", 1)[1].strip()
            elif any(phrase in lowered for phrase in trigger_phrases):
                candidate_text = line
            if not candidate_text:
                continue
            key = candidate_text.lower()
            if key in seen:
                continue
            seen.add(key)
            claim_candidates.append((candidate_text, raw_line.strip()[:400]))
        return claim_candidates[:30]

    def _extract_entity_candidates(self, text: str) -> list[tuple[str, int, str | None]]:
        stop_phrases = {
            "Current Plan",
            "Task Board",
            "Open Questions",
            "Target State",
            "Project Catalog",
        }
        phrase_counts: Counter[str] = Counter(
            match.group(0).strip()
            for match in re.finditer(r"\b[A-Z][A-Za-z0-9.&-]+(?:\s+[A-Z][A-Za-z0-9.&-]+){1,3}\b", text)
            if match.group(0).strip() not in stop_phrases
        )
        ranked: list[tuple[str, int, str | None]] = []
        for phrase, count in phrase_counts.most_common(25):
            snippet = self._first_matching_line(text, phrase)
            ranked.append((phrase, count, snippet))
        return ranked

    def _entity_type_hint(self, phrase: str) -> str:
        lowered = phrase.lower()
        if any(token in lowered for token in ("department", "agency", "bureau", "office", "university")):
            return "organization"
        if any(token in lowered for token in ("program", "reform", "policy", "act")):
            return "program"
        if any(token in lowered for token in ("county", "city", "jersey", "municipality")):
            return "geography"
        return "unknown"

    def _write_records(self, path: Path, records: list[Any], model_cls: type[BaseModel]) -> None:
        self.ensure_files_exist()
        normalized = [self._ensure_record_timestamps(model_cls.model_validate(item)).model_dump(mode="json") for item in records]
        path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")

    def _write_compiled_truth_outputs(self, report: dict[str, Any]) -> None:
        self.compiled_truth_report_path().write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.artifact_support_matrix_path().write_text(
            json.dumps(report.get("artifactSupportMatrix", []), indent=2) + "\n",
            encoding="utf-8",
        )
        self.paper_alignment_report_path().write_text(
            self._render_paper_alignment_markdown(report),
            encoding="utf-8",
        )
        self.compiled_truth_summary_path().write_text(
            self._render_compiled_truth_markdown(report),
            encoding="utf-8",
        )

    def _build_alignment_report(
        self,
        *,
        alignment_paths: list[str],
        claim_details: list[dict[str, Any]],
        source_details: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        checked_paths: list[str] = []
        has_partial_employment = any(
            item["claimKey"] == "claim-employment-provisional" and item["compiledStatus"] != "supported"
            for item in claim_details
        )
        has_proxy_income = any("income" in item["claimKey"] and item["compiledStatus"] != "supported" for item in claim_details)
        has_incomplete_zaf = any(
            item["claimKey"] == "claim-observed-zaf-incomplete"
            for item in claim_details
        )
        for rel_path in alignment_paths:
            target = (self.project_root / rel_path).resolve()
            if not target.exists():
                continue
            checked_paths.append(rel_path)
            text = target.read_text(encoding="utf-8", errors="ignore")
            lowered = text.lower()
            hedge_pattern = r"\b(preliminary|cautious|not|rather than|qualified|provisional|incomplete|estimated|proxy|derived|suggestive)\b"
            certainty_lines = [
                line.strip()
                for line in lowered.splitlines()
                if re.search(r"\b(definitive|conclusive|settled|proves)\b", line)
                or (" final " in f" {line} " and not re.search(hedge_pattern, line))
            ]
            if any(line and not re.search(hedge_pattern, line) for line in certainty_lines):
                issues.append(
                    {
                        "path": rel_path,
                        "severity": "warning",
                        "message": "Document uses stronger-than-supported certainty language.",
                    }
                )
            zaf_lines = [line.strip() for line in lowered.splitlines() if "observed zaf" in line]
            if has_incomplete_zaf and any(
                line and not re.search(r"\b(incomplete|partial|estimated|benchmark|not yet|limit)\b", line)
                for line in zaf_lines
            ):
                issues.append(
                    {
                        "path": rel_path,
                        "severity": "warning",
                        "message": "Observed ZAF language appears without a nearby incompleteness qualifier.",
                    }
                )
            if has_proxy_income and "median family income" in lowered and "acs" not in lowered and "proxy" not in lowered:
                issues.append(
                    {
                        "path": rel_path,
                        "severity": "warning",
                        "message": "Income discussion may be missing an ACS/proxy qualifier.",
                    }
                )
            employment_lines = [line.strip() for line in lowered.splitlines() if "employment" in line]
            if has_partial_employment and any(
                re.search(r"\b(settled|definitive|conclusive)\b", line) and not re.search(hedge_pattern, line)
                for line in employment_lines
            ):
                issues.append(
                    {
                        "path": rel_path,
                        "severity": "warning",
                        "message": "Employment discussion sounds more final than the current claim state.",
                    }
                )
        evidence_boundaries = [
            item["message"]
            for item in (
                {
                    "message": source["qualityNotes"],
                }
                for source in source_details
                if source.get("qualityNotes")
            )
        ]
        return {
            "checkedPaths": checked_paths,
            "issues": issues,
            "evidenceBoundaries": evidence_boundaries,
        }

    def _render_paper_alignment_markdown(self, report: dict[str, Any]) -> str:
        alignment = report.get("paperAlignment", {})
        lines = [
            "# Paper Alignment Report",
            "",
            f"- Generated at: {report.get('generatedAt')}",
            f"- Project status: {report.get('summary', {}).get('projectStatus', 'unknown')}",
            "",
            "## Checked Paths",
        ]
        checked_paths = alignment.get("checkedPaths", [])
        if checked_paths:
            lines.extend(f"- `{path}`" for path in checked_paths)
        else:
            lines.append("- No alignment paths were checked.")
        lines.extend(["", "## Issues"])
        issues = alignment.get("issues", [])
        if issues:
            for issue in issues:
                lines.append(f"- [{issue.get('severity', 'info')}] `{issue.get('path')}`: {issue.get('message')}")
        else:
            lines.append("- No heuristic alignment issues found.")
        return "\n".join(lines) + "\n"

    def _render_compiled_truth_markdown(self, report: dict[str, Any]) -> str:
        summary = report.get("summary", {})
        lines = [
            "# Compiled Truth Report",
            "",
            f"- Generated at: {report.get('generatedAt')}",
            f"- Project status: {summary.get('projectStatus', 'unknown')}",
            f"- Claims: {summary.get('claimCount', 0)}",
            f"- Artifacts: {summary.get('artifactCount', 0)}",
            f"- Sources: {summary.get('sourceCount', 0)}",
            f"- Source candidates: {summary.get('sourceCandidateCount', 0)}",
            f"- Claim candidates: {summary.get('claimCandidateCount', 0)}",
            f"- Entity candidates: {summary.get('entityCandidateCount', 0)}",
            f"- Conflicts: {summary.get('conflictCount', 0)}",
            "",
            "## Claims",
        ]
        for bucket in ("supported", "partiallyVerified", "needsEvidence", "stale", "blocked", "draft"):
            entries = report.get("claims", {}).get(bucket, [])
            lines.append(f"- {bucket}: {len(entries)}")
        lines.extend(["", "## Artifacts"])
        for bucket in ("verified", "partiallyVerified", "needsEvidence", "stale", "blocked", "draft"):
            entries = report.get("artifacts", {}).get(bucket, [])
            lines.append(f"- {bucket}: {len(entries)}")
        lines.extend(["", "## Exploration"])
        candidates = report.get("candidates", {})
        lines.append(f"- source candidates: {len(candidates.get('sourceCandidates', []))}")
        lines.append(f"- claim candidates: {len(candidates.get('claimCandidates', []))}")
        lines.append(f"- entity candidates: {len(candidates.get('entityCandidates', []))}")
        lines.append(f"- conflicts: {len(report.get('conflicts', []))}")
        lines.extend(["", "## Top Gaps"])
        gaps = report.get("sourceGaps", [])
        if gaps:
            for gap in gaps[:10]:
                label = gap.get("claimKey") or gap.get("artifactPath") or gap.get("sourceKey") or gap.get("path") or "gap"
                lines.append(f"- `{label}`: {gap.get('message')}")
        else:
            lines.append("- No current gaps recorded.")
        return "\n".join(lines) + "\n"

    def _normalize_timestamps(self, record: Any, preserve_created_at: str | None = None) -> Any:
        now = _utc_now()
        if getattr(record, "created_at", None) is None:
            record.created_at = preserve_created_at or now
        if preserve_created_at:
            record.created_at = preserve_created_at
        record.updated_at = now
        return record

    def _ensure_record_timestamps(self, record: Any) -> Any:
        now = _utc_now()
        if getattr(record, "created_at", None) is None:
            record.created_at = now
        if getattr(record, "updated_at", None) is None:
            record.updated_at = now
        return record


def sync_sources_from_configs(
    project_root: str | Path,
    *,
    sources_dir: str,
    source_keys: list[str],
) -> list[SourceRecord]:
    repo = ResearchIntegrityRepo(project_root)
    root = Path(project_root).resolve()
    synced: list[SourceRecord] = []
    for source_key in sorted(set(source_keys)):
        config_path = root / sources_dir / f"{source_key}.yaml"
        if not config_path.exists():
            continue
        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise ValueError(f"Invalid YAML in source config {config_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"Source config {config_path} must decode to a mapping")
        source_type = str(raw.get("type") or raw.get("source_type") or "api")
        admissibility_status = _infer_source_admissibility_from_config(raw)
        url_or_path = str(
            raw.get("url")
            or raw.get("path")
            or raw.get("storage_key")
            or raw.get("connection_string")
            or ((raw.get("download_urls") or [source_key])[0])
        )
        record = repo.upsert_source(
            {
                "source_key": source_key,
                "source_type": source_type,
                "title": str(raw.get("name") or source_key),
                "url_or_path": url_or_path,
                "origin": raw.get("publisher") or raw.get("provider") or raw.get("origin") or url_or_path,
                "acquired_at": _stringify_timestamp(raw.get("acquired_at") or raw.get("acquiredAt")) or _utc_now(),
                "retrieved_at": _stringify_timestamp(raw.get("retrieved_at") or raw.get("retrievedAt")) or _utc_now(),
                "access_method": raw.get("access_method") or raw.get("accessMethod") or source_type,
                "freshness_status": raw.get("freshness_status") or raw.get("freshnessStatus") or "fresh",
                "admissibility_status": admissibility_status,
                "impact_level": raw.get("impact_level") or raw.get("impactLevel") or "normal",
                "provenance": {
                    "config_path": str(config_path.relative_to(root)),
                    "path": raw.get("path"),
                    "url": raw.get("url"),
                    "storage_key": raw.get("storage_key"),
                    "response_path": raw.get("response_path"),
                    "derived_from": raw.get("derived_from") or raw.get("derivedFrom"),
                    "synthetic": bool(raw.get("synthetic")),
                    "estimated": bool(raw.get("estimated")),
                    "missing": bool(raw.get("missing")),
                    "fields": raw.get("fields") or [],
                },
                "quality_notes": raw.get("description"),
                "quality_status": "validated",
                "notes": raw.get("description"),
            }
        )
        synced.append(record)
    return synced


__all__ = [
    "ArtifactLineageRecord",
    "AssumptionRecord",
    "ClaimRecord",
    "ClaimCandidateRecord",
    "ConflictRecord",
    "EntityCandidateRecord",
    "EvidenceChunkRecord",
    "IntegrityEdgeRecord",
    "IntegrityIndexes",
    "ResearchIntegrityRepo",
    "SourceRecord",
    "SourceCandidateRecord",
    "STATE_FILE_NAMES",
    "VerificationRunRecord",
    "build_artifact_trust_summary",
    "build_claim_state",
    "build_source_state",
    "sync_sources_from_configs",
]
