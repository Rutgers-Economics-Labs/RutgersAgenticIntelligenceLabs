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
SourceImpactLevel = Literal["low", "normal", "high", "critical"]
ClaimStatus = Literal["draft", "supported", "unsupported", "needs_evidence", "superseded", "stale", "conflicted"]
EvidenceKind = Literal["direct", "derived", "contextual", "semantic_suggestion"]
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
    "artifact_lineage": "artifact_lineage.json",
    "verification_runs": "verification_runs.json",
    "evidence_chunks": "evidence_chunks.json",
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


class IntegrityIndexes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[AssumptionRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    artifact_lineage: list[ArtifactLineageRecord] = Field(default_factory=list)
    verification_runs: list[VerificationRunRecord] = Field(default_factory=list)
    evidence_chunks: list[EvidenceChunkRecord] = Field(default_factory=list)


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

    def artifact_lineage_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["artifact_lineage"]

    def verification_runs_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["verification_runs"]

    def evidence_chunks_path(self) -> Path:
        return self.state_root / STATE_FILE_NAMES["evidence_chunks"]

    def load_all(self) -> IntegrityIndexes:
        return IntegrityIndexes(
            assumptions=self.load_assumptions(),
            sources=self.load_sources(),
            claims=self.load_claims(),
            artifact_lineage=self.load_artifact_lineage(),
            verification_runs=self.load_verification_runs(),
            evidence_chunks=self.load_evidence_chunks(),
        )

    def rebuild_all(self) -> IntegrityIndexes:
        indexes = self.load_all()
        self.write_assumptions(indexes.assumptions)
        self.write_sources(indexes.sources)
        self.write_claims(indexes.claims)
        self.write_artifact_lineage(indexes.artifact_lineage)
        self.write_verification_runs(indexes.verification_runs)
        self.write_evidence_chunks(indexes.evidence_chunks)
        return indexes

    def load_assumptions(self) -> list[AssumptionRecord]:
        return self._load_records(self.assumptions_path(), AssumptionRecord)

    def write_assumptions(self, records: list[AssumptionRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.assumptions_path(), records, AssumptionRecord)

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
        self._write_records(self.sources_path(), records, SourceRecord)

    def upsert_source(self, record: SourceRecord | dict[str, Any]) -> SourceRecord:
        stored = self._upsert_by_key(self.load_sources, self.write_sources, SourceRecord, "source_key", record)
        self.rebuild_chunks_for_source(stored.source_key)
        return stored

    def update_source(self, source_key: str, **changes: Any) -> tuple[SourceRecord, list[ClaimRecord], list[ArtifactLineageRecord]]:
        records = self.load_sources()
        for idx, record in enumerate(records):
            if record.source_key != source_key:
                continue
            updated = record.model_copy(update=changes)
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

    def write_claims(self, records: list[ClaimRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.claims_path(), records, ClaimRecord)

    def upsert_claim(self, record: ClaimRecord | dict[str, Any]) -> ClaimRecord:
        stored = self._upsert_by_key(self.load_claims, self.write_claims, ClaimRecord, "claim_key", record)
        self.reconcile_claim_conflicts()
        self.reconcile_artifact_claim_support()
        return self.get_claim(stored.claim_key) or stored

    def load_artifact_lineage(self) -> list[ArtifactLineageRecord]:
        return self._load_records(self.artifact_lineage_path(), ArtifactLineageRecord)

    def write_artifact_lineage(self, records: list[ArtifactLineageRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.artifact_lineage_path(), records, ArtifactLineageRecord)

    def upsert_artifact_lineage(self, record: ArtifactLineageRecord | dict[str, Any]) -> ArtifactLineageRecord:
        stored = self._upsert_by_key(
            self.load_artifact_lineage,
            self.write_artifact_lineage,
            ArtifactLineageRecord,
            "artifact_path",
            record,
        )
        self.reconcile_artifact_claim_support()
        return next(
            (item for item in self.load_artifact_lineage() if item.artifact_path == stored.artifact_path),
            stored,
        )

    def load_verification_runs(self) -> list[VerificationRunRecord]:
        return self._load_records(self.verification_runs_path(), VerificationRunRecord)

    def write_verification_runs(self, records: list[VerificationRunRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.verification_runs_path(), records, VerificationRunRecord)

    def upsert_verification_run(self, record: VerificationRunRecord | dict[str, Any]) -> VerificationRunRecord:
        return self._upsert_by_key(
            self.load_verification_runs,
            self.write_verification_runs,
            VerificationRunRecord,
            "run_id",
            record,
        )

    def load_evidence_chunks(self) -> list[EvidenceChunkRecord]:
        return self._load_records(self.evidence_chunks_path(), EvidenceChunkRecord)

    def write_evidence_chunks(self, records: list[EvidenceChunkRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.evidence_chunks_path(), records, EvidenceChunkRecord)

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

        source_claims = {
            source.source_key: self.claims_for_source(source.source_key)
            for source in indexes.sources
        }
        source_artifacts = {
            source.source_key: self.artifacts_for_source(source.source_key)
            for source in indexes.sources
        }
        claim_artifacts = {
            claim.claim_key: self.artifacts_for_claim(claim.claim_key)
            for claim in indexes.claims
        }

        artifact_sources = {
            artifact.artifact_path: [
                source_index[key]
                for key in {_normalize_reference_key(reference) for reference in artifact.sources}
                if key in source_index
            ]
            for artifact in indexes.artifact_lineage
        }
        artifact_claims = {
            artifact.artifact_path: [
                claim_index[key]
                for key in {_normalize_reference_key(reference) for reference in artifact.claims}
                if key in claim_index
            ]
            for artifact in indexes.artifact_lineage
        }
        chunk_index = {item.chunk_key: item for item in indexes.evidence_chunks}
        chunk_claims = {
            chunk.chunk_key: [
                claim
                for claim in indexes.claims
                if chunk.chunk_key in claim.evidence_chunk_keys
            ]
            for chunk in indexes.evidence_chunks
        }

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
                    )
                    for claim in source_claims.get(source.source_key, []):
                        if not _claim_is_explicit(claim):
                            continue
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
                        )
                    for artifact in source_artifacts.get(source.source_key, []):
                        if not _artifact_is_explicit(artifact):
                            continue
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
                    )
            elif record_type == "claim":
                claim = candidate["record"]
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
                    )
            elif record_type == "artifact":
                artifact = candidate["record"]
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
                    )
                    for claim in artifact_claims.get(artifact.artifact_path, []):
                        if not _claim_is_explicit(claim):
                            continue
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
                    )
            else:
                chunk = candidate["record"]
                source = source_index.get(chunk.source_key)
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
                    )
                    for claim in chunk_claims.get(chunk.chunk_key, []):
                        if not _claim_is_explicit(claim):
                            continue
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
        try:
            return [model_cls.model_validate(item) for item in raw]
        except ValidationError as exc:
            raise ValueError(f"Invalid integrity records in {path}: {exc}") from exc

    def _write_records(self, path: Path, records: list[Any], model_cls: type[BaseModel]) -> None:
        self.ensure_files_exist()
        normalized = [self._ensure_record_timestamps(model_cls.model_validate(item)).model_dump(mode="json") for item in records]
        path.write_text(json.dumps(normalized, indent=2) + "\n", encoding="utf-8")

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
                "impact_level": raw.get("impact_level") or raw.get("impactLevel") or "normal",
                "provenance": {
                    "config_path": str(config_path.relative_to(root)),
                    "path": raw.get("path"),
                    "url": raw.get("url"),
                    "storage_key": raw.get("storage_key"),
                    "response_path": raw.get("response_path"),
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
    "EvidenceChunkRecord",
    "IntegrityIndexes",
    "ResearchIntegrityRepo",
    "SourceRecord",
    "STATE_FILE_NAMES",
    "VerificationRunRecord",
    "sync_sources_from_configs",
]
