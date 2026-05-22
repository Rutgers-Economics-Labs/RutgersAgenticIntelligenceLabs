"""
Research Loop Closure — orchestrates the transition from session outputs to project state.

Updates claims.json, sources.json, and research artifacts (draft_memo.md) 
based on certified SessionResults.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.runners.contracts import SessionResult, TrustState, SourceMaterializationState
from app.services import integrity_service, artifact_service

logger = logging.getLogger(__name__)

def apply_session_results(project_root: Path, result: SessionResult) -> dict[str, Any]:
    """
    The main coordinator for updating project state after a session.
    """
    updates = {
        "claims_added": 0,
        "sources_updated": 0,
        "memo_updated": False,
        "trust_changes": 0
    }
    
    # 1. Update Claims
    if result.claims:
        repo = integrity_service.get_integrity_repo(project_root)
        for claim in result.claims:
            # Map granular TrustState to legacy ClaimStatus literals
            status_map = {
                TrustState.CANDIDATE: "draft",
                TrustState.VERIFIED: "supported",
                TrustState.REJECTED: "unsupported",
                TrustState.SUPERSEDED: "superseded",
                TrustState.PARTIALLY_VERIFIED: "supported" # Fallback
            }
            legacy_status = status_map.get(claim.status, "draft")

            repo.upsert_claim({
                "claim_key": claim.claim_id,
                "claim_text": claim.text,
                "status": legacy_status,
                "evidence_paths": claim.evidence_refs,
                "confidence": claim.confidence,
                # 'notes' and 'candidate' status are not supported by rail-py yet
            })
            updates["claims_added"] += 1

    # 2. Update Sources
    if result.sources:
        repo = integrity_service.get_integrity_repo(project_root)
        for source in result.sources:
            repo.upsert_source({
                "source_key": source.source_id,
                "title": source.name,
                "provider": source.provider,
                "url_or_path": source.access_url,
                "access_method": source.access_method,
                "admissibility_status": source.admissibility,
                "notes": source.notes
                # Track B materialization state is currently in ledger, 
                # but we can also store it in the source record notes.
            })
            updates["sources_updated"] += 1

    # 3. Update Draft Memo (Item 9)
    if result.summary and (result.claims or result.task_type.value == "analysis"):
        artifact_service.update_draft_memo(project_root, result.summary)
        updates["memo_updated"] = True

    # 4. Apply Trust Changes (Track B)
    for change in result.trust_changes:
        # This will eventually call into integrity_service to promote/demote
        logger.info(f"Loop Closure: Trust change requested for {change.object_type}:{change.object_id} ({change.from_state} -> {change.to_state})")
        updates["trust_changes"] += 1
        
    return updates
