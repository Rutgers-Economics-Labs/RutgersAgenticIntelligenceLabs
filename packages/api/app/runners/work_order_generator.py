"""WorkOrder generator — translate planner task dispatch parameters into a typed WorkOrder.

Called from create_runner_session just before the runner is launched.

The generated work order is written to:
  - workspace_root/research_plan/work_orders/<wo_id>.json  (agent-visible)
  - project_root/research_plan/work_orders/<wo_id>.json    (audit trail)

This is a best-effort mapping.  Fields the planner hasn't yet declared
(capabilities_required, outputs_required) get conservative defaults so the
work order is valid even for legacy task dispatches.  The planner can declare
richer values by adding a ``taskType`` and ``capabilities`` field on the Convex
task record; these take precedence over the role-based defaults.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runners.contracts import Capability, TaskType, WorkOrder


# ---------------------------------------------------------------------------
# Role → TaskType default mapping
# ---------------------------------------------------------------------------

_ROLE_TO_TASK_TYPE: dict[str, TaskType] = {
    "research": TaskType.ANALYSIS,
    "analysis": TaskType.ANALYSIS,
    "data": TaskType.DATA_INGESTION,
    "artifact": TaskType.ARTIFACT_WRITING,
    "health": TaskType.HEALTH_REPAIR,
    "repair": TaskType.HEALTH_REPAIR,
    "claim": TaskType.CLAIM_EXTRACTION,
    "verification": TaskType.VERIFICATION,
    "source": TaskType.SOURCE_DISCOVERY,
    "coding": TaskType.ANALYSIS,
    "planner": TaskType.ANALYSIS,
}


# ---------------------------------------------------------------------------
# TaskType → default capabilities
# ---------------------------------------------------------------------------

_TASK_TYPE_CAPABILITIES: dict[TaskType, list[Capability]] = {
    TaskType.DATA_INGESTION: [Capability.EDIT_FILES, Capability.FETCH_REMOTE_DATA],
    TaskType.ANALYSIS: [Capability.EXECUTE_PYTHON, Capability.QUERY_DUCKDB],
    TaskType.SOURCE_DISCOVERY: [Capability.BROWSE_WEB, Capability.EDIT_FILES],
    TaskType.ARTIFACT_WRITING: [Capability.EDIT_FILES, Capability.WRITE_LONG_ARTIFACTS],
    TaskType.HEALTH_REPAIR: [Capability.EDIT_FILES, Capability.RUN_SHELL],
    TaskType.CLAIM_EXTRACTION: [Capability.EDIT_FILES, Capability.WRITE_STRUCTURED_OUTPUT],
    TaskType.VERIFICATION: [Capability.RUN_SHELL, Capability.WRITE_STRUCTURED_OUTPUT],
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_task_type(role: str, task: dict[str, Any] | None) -> TaskType:
    """Infer TaskType from agent role and optional task metadata.

    Priority:
      1. ``taskType`` / ``task_type`` field on the Convex task record (explicit).
      2. Role-based default from ``_ROLE_TO_TASK_TYPE``.
      3. Fallback: DATA_INGESTION (conservative choice for unknown roles).
    """
    if task:
        raw = str(task.get("taskType") or task.get("task_type") or "").strip().lower()
        try:
            return TaskType(raw)
        except ValueError:
            pass

    role_key = str(role or "").strip().lower()
    return _ROLE_TO_TASK_TYPE.get(role_key, TaskType.DATA_INGESTION)


def _infer_capabilities(task_type: TaskType, task: dict[str, Any] | None) -> list[Capability]:
    """Return capability requirements, preferring explicit task metadata."""
    if task:
        raw_list = task.get("capabilities") or task.get("capabilities_required") or []
        caps = []
        for item in raw_list:
            try:
                caps.append(Capability(str(item).strip().lower()))
            except ValueError:
                pass
        if caps:
            return caps
    return _TASK_TYPE_CAPABILITIES.get(task_type, [Capability.EDIT_FILES])


def _infer_expected_progress(task_type: TaskType) -> dict[str, Any]:
    """Provide structured expected progress based on task type (Track B)."""
    if task_type == TaskType.ANALYSIS:
        return {"one_of": [
            "claim_candidate_created",
            "hypothesis_rejected_with_evidence",
            "analysis_dataset_missing_declared",
            "method_blocker_declared"
        ]}
    elif task_type == TaskType.DATA_INGESTION:
        return {"one_of": [
            "new_remote_source_fetched",
            "source_marked_inadmissible",
            "source_marked_unavailable_with_reason",
            "replacement_source_registered"
        ]}
    elif task_type == TaskType.ARTIFACT_WRITING:
        return {"one_of": [
            "draft_artifact_created",
            "artifact_updated",
            "promotion_blocker_declared"
        ]}
    return {"one_of": ["domain_progress_recorded", "typed_blocker_declared", "scope_reduced_with_reason"]}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_work_order(
    *,
    session_id: str,
    project_slug: str,
    role: str,
    task_id: str | None,
    task: dict[str, Any] | None,
    allowed_paths: list[str],
    runner_name: str | None,
) -> WorkOrder:
    """Generate a WorkOrder for a new session dispatch."""
    task_type = _infer_task_type(role, task)
    capabilities = _infer_capabilities(task_type, task)
    
    expected_progress = _infer_expected_progress(task_type)
    failure_policy = {"max_attempts": 2, "if_no_progress": "downgrade_or_escalate"}

    # Stable work order ID: deterministic from project + task (or session).
    # Using a hash keeps the ID compact and safe for filenames.
    wo_seed = f"{project_slug}:{task_id or session_id}"
    wo_hash = hashlib.sha256(wo_seed.encode()).hexdigest()[:12]
    wo_id = f"wo_{wo_hash}"
    
    # Track B: Idempotency and hashing
    idempotency_key = f"{project_slug}:{task_type.value}:{task_id or session_id}"
    input_hash = None
    if task:
        # A simple stable hash of the task dictionary state
        input_hash = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()[:16]

    # Sanitise allowed_paths — the WorkOrder validator requires relative paths.
    safe_paths = [
        p for p in (allowed_paths or [])
        if p and not p.startswith("/") and ".." not in p.split("/")
    ]
    if not safe_paths:
        safe_paths = ["research_plan/"]

    from app.runners.contracts import ExpectedProgress, FailurePolicy
    return WorkOrder(
        work_order_id=wo_id,
        project_slug=project_slug,
        task_type=task_type,
        expected_progress=ExpectedProgress(**expected_progress),
        failure_policy=FailurePolicy(**failure_policy),
        idempotency_key=idempotency_key,
        input_hash=input_hash,
        capabilities_required=capabilities,
        runner_preferred=runner_name,
        allowed_paths=safe_paths,
        created_by=session_id,
        created_at=datetime.now(timezone.utc),
    )


def write_work_order(
    work_order: WorkOrder,
    *,
    workspace_root: Path,
    project_root: Path | None = None,
) -> Path:
    """Persist a work order to disk in JSON format.

    Writes to both the workspace (agent-visible) and the project root
    (audit trail), creating directories as needed.

    Args:
        work_order: The WorkOrder instance to write.
        workspace_root: Agent workspace directory.
        project_root: Project root for the audit-trail copy.  Pass None to
            skip the audit copy (e.g. in local-only sessions).

    Returns:
        Absolute path to the workspace copy of the work order JSON.
    """
    payload = json.loads(work_order.model_dump_json())

    wo_dir = workspace_root / "research_plan" / "work_orders"
    wo_dir.mkdir(parents=True, exist_ok=True)
    wo_path = wo_dir / f"{work_order.work_order_id}.json"
    wo_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # Mirror to project root for audit trail (skipped if roots are identical).
    if project_root and project_root.resolve() != workspace_root.resolve():
        audit_dir = project_root / "research_plan" / "work_orders"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / f"{work_order.work_order_id}.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    return wo_path
