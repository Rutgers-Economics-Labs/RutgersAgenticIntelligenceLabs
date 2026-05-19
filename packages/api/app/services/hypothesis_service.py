from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services import planner_service
from app.runners import session_lifecycle
from rail.integrity import ConflictRecord, ResearchIntegrityRepo
from rail.manifest import load_manifest


ALLOWED_HYPOTHESIS_STATUSES = {"draft", "supported", "weakened", "rejected", "archived"}


def _project_root(project: dict[str, Any]) -> Path:
    root = planner_service.project_root_from_record(project)
    if root is None:
        raise ValueError("Project repo not found")
    return root


def run_critic_review(project: dict[str, Any], hypothesis_ids: list[str] | None = None) -> dict[str, Any]:
    root = _project_root(project)
    repo = ResearchIntegrityRepo(root, plan_root="research_plan")
    indexes = repo.load_all()

    selected = set(item.strip() for item in (hypothesis_ids or []) if item and item.strip())
    hypotheses = [h for h in indexes.hypotheses if not selected or h.hypothesis_id in selected]
    claims_by_key = {item.claim_key: item for item in indexes.claims}

    created_conflicts: list[str] = []
    created_claim_candidates: list[str] = []
    updated_hypotheses: list[dict[str, Any]] = []

    for hypothesis in hypotheses:
        linked_claims = [claims_by_key[key] for key in hypothesis.claim_keys if key in claims_by_key]
        blocking_claims = [
            claim for claim in linked_claims if claim.status in {"draft", "unsupported", "needs_evidence", "stale", "conflicted"}
        ]
        hypothesis_next_status = hypothesis.status
        if blocking_claims and hypothesis.status not in {"rejected", "archived"}:
            hypothesis_next_status = "weakened"
        elif linked_claims and not blocking_claims and hypothesis.status in {"draft", "weakened"}:
            hypothesis_next_status = "supported"
        if hypothesis_next_status != hypothesis.status:
            updated = repo.update_hypothesis(hypothesis.hypothesis_id, status=hypothesis_next_status)
            updated_hypotheses.append(updated.model_dump(mode="json", by_alias=True))

        for claim in blocking_claims:
            conflict_key = f"critic-{hypothesis.hypothesis_id}-{claim.claim_key}"
            existing = repo.get_conflict(conflict_key)
            if existing is None:
                payload = {
                    "conflict_key": conflict_key,
                    "left_ref": f"research_plan/state/hypotheses.json#{hypothesis.hypothesis_id}",
                    "right_ref": f"research_plan/state/claims.json#{claim.claim_key}",
                    "conflict_type": "critic_blocker",
                    "status": "open",
                    "explanation": (
                        f"Hypothesis {hypothesis.hypothesis_id} is linked to claim {claim.claim_key} "
                        f"with unresolved status {claim.status}."
                    ),
                    "recommended_resolution": "Resolve claim evidence or update hypothesis status before promotion.",
                }
                current_conflicts = repo.load_conflicts()
                persisted = ConflictRecord.model_validate(payload)
                current_conflicts.append(persisted)
                repo._persist_conflicts(current_conflicts)  # type: ignore[attr-defined]
                created_conflicts.append(persisted.conflict_key)

            candidate_key = f"critic-{hypothesis.hypothesis_id}-{claim.claim_key}"
            candidate = repo.get_claim_candidate(candidate_key)
            if candidate is None:
                created = repo.upsert_claim_candidate(
                    {
                        "candidate_key": candidate_key,
                        "claim_text": (
                            f"Reassess claim {claim.claim_key} linked to hypothesis "
                            f"{hypothesis.hypothesis_id} due to status {claim.status}."
                        ),
                        "status": "candidate",
                        "discovered_in_paths": [
                            "research_plan/state/hypotheses.json",
                            "research_plan/state/claims.json",
                        ],
                        "evidence_paths": list(claim.evidence_paths),
                        "source_candidate_keys": [],
                        "snippet": claim.claim_text[:280],
                    }
                )
                created_claim_candidates.append(created.candidate_key)

    return {
        "reviewedHypothesisIds": [item.hypothesis_id for item in hypotheses],
        "updatedHypotheses": updated_hypotheses,
        "createdConflicts": created_conflicts,
        "createdClaimCandidates": created_claim_candidates,
    }


async def run_research_burst(
    project: dict[str, Any],
    *,
    objective: str,
    max_parallel: int | None = None,
) -> dict[str, Any]:
    root = _project_root(project)
    manifest = load_manifest(root)
    cfg = manifest.research_burst
    if not cfg.enabled:
        raise ValueError("research_burst is disabled in rail.yaml")

    configured_max = int(cfg.max_parallel)
    requested = int(max_parallel) if max_parallel is not None else configured_max
    if requested < 1:
        raise ValueError("max_parallel must be at least 1")
    parallel = min(requested, configured_max, 8)

    repo = ResearchIntegrityRepo(root, plan_root="research_plan")
    existing = {item.hypothesis_id for item in repo.load_hypotheses()}
    created: list[dict[str, Any]] = []
    objective_slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in objective).strip("-")[:32] or "burst"
    for idx in range(parallel):
        hypothesis_id = f"burst-{objective_slug}-{idx + 1:02d}"
        if hypothesis_id in existing:
            continue
        record = repo.upsert_hypothesis(
            {
                "id": hypothesis_id,
                "statement": f"{objective.strip()} (angle {idx + 1})",
                "scope": "research_burst",
                "falsifiers": [f"Angle {idx + 1} evidence contradicts expected trend."],
                "status": "draft",
                "score": None,
                "task_ids": [],
                "claim_keys": [],
                "artifact_paths": [],
                "human_notes": f"Generated by research burst with max_parallel={parallel}.",
            }
        )
        created.append(record.model_dump(mode="json", by_alias=True))

    decisions_path = root / "research_plan" / "decisions.md"
    if decisions_path.exists():
        with decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n"
                f"- research_burst objective='{objective.strip()}' requested={requested} "
                f"applied={parallel} created={len(created)}\n"
            )

    created_tasks: list[dict[str, Any]] = []
    board = await planner_service.ensure_main_board(project)
    for item in created:
        title = f"Evaluate hypothesis {item['id']}"
        task = await planner_service.create_task(
            project=project,
            board_id=board["_id"],
            title=title,
            description=f"Collect evidence and update status for hypothesis {item['id']}.",
            status="ready",
            agent_role="research",
            repo_paths=["research_plan/state/hypotheses.json", "research_plan/state/claims.json", "artifacts"],
            acceptance_criteria=[
                f"hypothesis {item['id']} status is updated with evidence-backed rationale",
                "linked claims and artifacts are updated when evidence shifts",
            ],
            depends_on_task_ids=[],
            priority="high",
        )
        created_tasks.append(task)

    launched_sessions: list[dict[str, Any]] = []
    for task in created_tasks[:parallel]:
        try:
            result = await session_lifecycle.create_runner_session(
                project_id=project["_id"],
                project_slug=project["slug"],
                task_id=str(task["_id"]),
                runner_name="codex_cli",
                role=task["agentRole"],
                task_description=task["description"],
                repo_url=project.get("gitRepoUrl") or "",
                branch=project.get("defaultBranch") or "main",
                local_repo_path=project.get("localRepoPath"),
                allowed_paths=task.get("repoPaths") or [],
                acceptance_criteria=task.get("acceptanceCriteria") or [],
                agent_role_for_secrets=task["agentRole"],
                policy_approval_granted=True,
            )
            await planner_service.update_task(
                str(task["_id"]),
                project=project,
                status="running",
                approval_state="granted",
                runner="codex_cli",
                latestRunSummary=f"Research burst launched session {result['convex_session_id']}",
            )
            launched_sessions.append(
                {
                    "taskId": str(task["_id"]),
                    "sessionId": result.get("convex_session_id"),
                }
            )
        except Exception:
            await planner_service.update_task(
                str(task["_id"]),
                project=project,
                status="ready",
                latestRunSummary="Research burst launch deferred; start manually from task board.",
            )

    burst_tasks: list[dict[str, Any]] = []
    for task in created_tasks:
        burst_tasks.append(
            {
                "_id": str(task.get("_id") or ""),
                "title": str(task.get("title") or ""),
                "description": str(task.get("description") or ""),
                "status": str(task.get("status") or "ready"),
                "agentRole": str(task.get("agentRole") or "research"),
            }
        )

    return {
        "objective": objective,
        "requestedParallel": requested,
        "appliedParallel": parallel,
        "configuredMaxParallel": configured_max,
        "createdHypotheses": created,
        "suggestedTasks": burst_tasks,
        "launchedSessions": launched_sessions,
        "budget": {
            "maxCostUsd": cfg.max_cost_usd,
        },
    }

