from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


AssumptionStatus = Literal["active", "needs_review", "superseded", "rejected"]
SourceQualityStatus = Literal["candidate", "validated", "blocked", "rejected"]
ClaimStatus = Literal["draft", "supported", "unsupported", "needs_evidence", "superseded"]
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

STATE_FILE_NAMES = {
    "assumptions": "assumptions.json",
    "sources": "sources.json",
    "claims": "claims.json",
    "artifact_lineage": "artifact_lineage.json",
    "verification_runs": "verification_runs.json",
}


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_source_path(file_name: str) -> str:
    return f"research_plan/state/{file_name}"


def _normalize_reference_key(reference: str) -> str:
    return reference.split("#", 1)[-1].strip()


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
    status: ClaimStatus = "draft"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["claims"]))
    caveats: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class ArtifactLineageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_path: str
    artifact_type: str
    title: str
    promotion_state: PromotionState = "draft"
    inputs: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
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
    task_id: str | None = None
    agent_session_id: str | None = None
    status: VerificationStatus
    checks: list[dict[str, Any]] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    source_path: str = Field(default_factory=lambda: _default_source_path(STATE_FILE_NAMES["verification_runs"]))
    created_at: str | None = None
    updated_at: str | None = None


class IntegrityIndexes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[AssumptionRecord] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    artifact_lineage: list[ArtifactLineageRecord] = Field(default_factory=list)
    verification_runs: list[VerificationRunRecord] = Field(default_factory=list)


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

    def load_all(self) -> IntegrityIndexes:
        return IntegrityIndexes(
            assumptions=self.load_assumptions(),
            sources=self.load_sources(),
            claims=self.load_claims(),
            artifact_lineage=self.load_artifact_lineage(),
            verification_runs=self.load_verification_runs(),
        )

    def rebuild_all(self) -> IntegrityIndexes:
        indexes = self.load_all()
        self.write_assumptions(indexes.assumptions)
        self.write_sources(indexes.sources)
        self.write_claims(indexes.claims)
        self.write_artifact_lineage(indexes.artifact_lineage)
        self.write_verification_runs(indexes.verification_runs)
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
        return self._upsert_by_key(self.load_sources, self.write_sources, SourceRecord, "source_key", record)

    def load_claims(self) -> list[ClaimRecord]:
        return self._load_records(self.claims_path(), ClaimRecord)

    def write_claims(self, records: list[ClaimRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.claims_path(), records, ClaimRecord)

    def upsert_claim(self, record: ClaimRecord | dict[str, Any]) -> ClaimRecord:
        return self._upsert_by_key(self.load_claims, self.write_claims, ClaimRecord, "claim_key", record)

    def load_artifact_lineage(self) -> list[ArtifactLineageRecord]:
        return self._load_records(self.artifact_lineage_path(), ArtifactLineageRecord)

    def write_artifact_lineage(self, records: list[ArtifactLineageRecord] | list[dict[str, Any]]) -> None:
        self._write_records(self.artifact_lineage_path(), records, ArtifactLineageRecord)

    def upsert_artifact_lineage(self, record: ArtifactLineageRecord | dict[str, Any]) -> ArtifactLineageRecord:
        return self._upsert_by_key(
            self.load_artifact_lineage,
            self.write_artifact_lineage,
            ArtifactLineageRecord,
            "artifact_path",
            record,
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

    def artifacts_for_assumption(self, assumption_key: str) -> list[ArtifactLineageRecord]:
        return [
            record
            for record in self.load_artifact_lineage()
            if assumption_key in {_normalize_reference_key(reference) for reference in record.assumptions}
        ]

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


__all__ = [
    "ArtifactLineageRecord",
    "AssumptionRecord",
    "ClaimRecord",
    "IntegrityIndexes",
    "ResearchIntegrityRepo",
    "SourceRecord",
    "STATE_FILE_NAMES",
    "VerificationRunRecord",
]
