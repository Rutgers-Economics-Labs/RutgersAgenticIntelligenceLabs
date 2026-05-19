"""Research-time integrity helpers: persist grounded claims to claims.json.

Used by the live agent loop and any worker that needs to publish supported
claims tied to existing sources and an artifact. This is the missing wiring
between research output and the integrity ledger.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Sequence

from rail.integrity import ClaimRecord, ResearchIntegrityRepo


def _slugify(text: str, *, max_len: int = 48) -> str:
    cleaned = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in text.lower().strip()
    )
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:max_len] or "claim"


def claim_key_for(text: str, *, prefix: str = "claim") -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    slug = _slugify(text)
    return f"{prefix}-{slug}-{digest}" if slug else f"{prefix}-{digest}"


def publish_grounded_claims(
    project_root: str | Path,
    *,
    claims: Sequence[dict[str, Any]],
    artifact_path: str | None = None,
    plan_root: str = "research_plan",
) -> list[ClaimRecord]:
    """Persist a list of grounded claims and trigger integrity-edge rebuild.

    Each claim dict requires `text` and at least one of `source_keys`,
    `evidence_paths`, `evidence_chunk_keys` to be promoted to `supported`.
    Optional fields: `claim_key`, `confidence`, `evidence_kind`, `caveats`,
    `open_questions`. `artifact_path` is recorded on every claim so the
    integrity edge rebuild can connect claim → artifact.
    """
    repo = ResearchIntegrityRepo(project_root, plan_root=plan_root)
    repo.ensure_files_exist()

    stored: list[ClaimRecord] = []
    for spec in claims:
        text = str(spec.get("text") or spec.get("claim_text") or "").strip()
        if not text:
            continue
        key = str(spec.get("claim_key") or "").strip() or claim_key_for(text)
        record: dict[str, Any] = {
            "claim_key": key,
            "claim_text": text,
            "status": "supported",
            "source_keys": list(spec.get("source_keys") or []),
            "evidence_paths": list(spec.get("evidence_paths") or []),
            "evidence_chunk_keys": list(spec.get("evidence_chunk_keys") or []),
            "caveats": list(spec.get("caveats") or []),
            "open_questions": list(spec.get("open_questions") or []),
        }
        if artifact_path:
            record["artifact_path"] = artifact_path
        if spec.get("confidence") is not None:
            record["confidence"] = float(spec["confidence"])
        if spec.get("evidence_kind"):
            record["evidence_kind"] = spec["evidence_kind"]
        stored.append(repo.upsert_claim(record))
    return stored


def claim_evidence_links_block(
    claim_keys: Iterable[str],
    *,
    source_keys: Iterable[str] = (),
    plan_root: str = "research_plan",
) -> str:
    """Render an `Evidence Links` markdown block referencing claims.json and sources.json.

    Used by artifact writers so the artifact-workflow contract sees the
    `Evidence Links` heading plus at least one `claims.json#…` reference.
    """
    claim_list = list(claim_keys)
    source_list = list(source_keys)
    lines = ["## Evidence Links", ""]
    for key in claim_list:
        lines.append(f"- claim: `{plan_root}/state/claims.json#{key}`")
    for key in source_list:
        lines.append(f"- source: `{plan_root}/state/sources.json#{key}`")
    if not claim_list and not source_list:
        lines.append("- _no grounded claims linked_")
    return "\n".join(lines) + "\n"
