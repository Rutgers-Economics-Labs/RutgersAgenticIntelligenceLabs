"""Lifecycle contracts for local execution and KRAIL workflow delegation."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock

from app.krail_runtime.contracts import KrailRuntime, ProjectRef, RunRequest

from .errors import InvalidTransitionError
from .models import PermissionProfile, RunEvent, RunRecord, RunStatus, TERMINAL_STATUSES
from .store import InMemoryRunStore


class ExecutionService:
    _allowed = {
        RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
        RunStatus.RUNNING: {RunStatus.WAITING_APPROVAL, RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED},
        RunStatus.WAITING_APPROVAL: {RunStatus.RUNNING, RunStatus.CANCELLED},
    }

    def __init__(self, store: InMemoryRunStore, runtime: KrailRuntime | None = None) -> None:
        self.store, self.runtime = store, runtime
        self._cancellations: dict[str, Event] = {}
        self._profile_limits: dict[str, PermissionProfile] = {}
        self._running_by_profile: dict[str, int] = {}
        self._lock = RLock()

    def create_run(self, *, project_id: str, project_path: Path, kind: str, profile: PermissionProfile,
                   baseline_commit: str | None = None, workflow_id: str | None = None,
                   project_read_only: bool = False) -> RunRecord:
        existing = self._profile_limits.get(profile.name)
        if existing is not None and existing != profile:
            raise ValueError(f"Conflicting permission profile snapshot for {profile.name}")
        record = self.store.create(RunRecord(project_id=project_id, project_path=project_path.resolve(), kind=kind,
            permission_profile=profile, baseline_commit=baseline_commit, workflow_id=workflow_id,
            project_read_only=project_read_only))
        self._profile_limits.setdefault(profile.name, profile)
        self._cancellations[record.run_id] = Event()
        self.append_event(record.run_id, "queued", "Run queued")
        return record

    def transition(self, run_id: str, status: RunStatus, *, result: dict | None = None) -> RunRecord:
        with self._lock:
            record = self.store.get(run_id)
            if status not in self._allowed.get(record.status, set()):
                raise InvalidTransitionError(f"Cannot transition {record.status} to {status}")
            if status is RunStatus.RUNNING and record.status is not RunStatus.RUNNING:
                current = self._running_by_profile.get(record.permission_profile.name, 0)
                if current >= self._profile_limits[record.permission_profile.name].max_concurrency:
                    raise InvalidTransitionError(f"Concurrency limit reached for profile {record.permission_profile.name}")
                self._running_by_profile[record.permission_profile.name] = current + 1
            if record.status is RunStatus.RUNNING and status in TERMINAL_STATUSES | {RunStatus.WAITING_APPROVAL}:
                name = record.permission_profile.name
                self._running_by_profile[name] = max(0, self._running_by_profile.get(name, 1) - 1)
            updated = record.model_copy(update={"status": status, "updated_at": datetime.now(timezone.utc),
                                                "result": result if result is not None else record.result})
            self.store.replace(updated)
            self.append_event(run_id, status.value, f"Run {status.value}", result or {})
            return updated

    def append_event(self, run_id: str, kind: str, message: str, data: dict | None = None) -> RunEvent:
        return self.store.append_event(RunEvent(run_id=run_id, kind=kind, message=message, data=data or {}))

    def events(self, run_id: str) -> list[RunEvent]:
        return self.store.events(run_id)

    def cancellation_hook(self, run_id: str) -> Event:
        return self._cancellations[run_id]

    def cancel(self, run_id: str) -> RunRecord:
        self.cancellation_hook(run_id).set()
        record = self.store.get(run_id)
        if record.status in TERMINAL_STATUSES:
            return record
        return self.transition(run_id, RunStatus.CANCELLED)

    def execute_krail_workflow(self, run_id: str, request: RunRequest) -> RunRecord:
        if self.runtime is None:
            raise RuntimeError("KrailRuntime is required for workflow execution")
        record = self.transition(run_id, RunStatus.RUNNING)
        if record.project_read_only:
            return self.transition(run_id, RunStatus.FAILED, result={"error": "Registered project is read-only"})
        try:
            handle = self.runtime.execute_workflow(ProjectRef(project_id=record.project_id, path=record.project_path, read_only=record.project_read_only), request)
            # Cancellation may have won while the synchronous runtime call was in progress.
            if self.store.get(run_id).status is RunStatus.CANCELLED:
                return self.store.get(run_id)
            if handle.status in {"waiting_approval", "pending_approval"}:
                return self.transition(run_id, RunStatus.WAITING_APPROVAL, result=handle.model_dump())
            if handle.status in {"failed", "error"}:
                return self.transition(run_id, RunStatus.FAILED, result=handle.model_dump())
            return self.transition(run_id, RunStatus.SUCCEEDED, result=handle.model_dump())
        except Exception as exc:
            if self.store.get(run_id).status is RunStatus.CANCELLED:
                return self.store.get(run_id)
            return self.transition(run_id, RunStatus.FAILED, result={"error": str(exc)})
