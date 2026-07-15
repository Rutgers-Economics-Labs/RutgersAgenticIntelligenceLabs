"""Bounded, single-node background execution supervisor.

Workers are intentionally process-local. Restart reconciliation is performed by
ExecutionService; distributed scheduling/locking is deferred to a future service.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from app.krail_runtime.contracts import RunRequest

from .service import ExecutionService


class LocalRunSupervisor:
    def __init__(self, service: ExecutionService, *, max_workers: int = 4) -> None:
        self.service = service
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="krail-run")
        self._submitted: set[str] = set()
        self._lock = RLock()

    def submit_workflow(self, run_id: str, request: RunRequest) -> None:
        with self._lock:
            if run_id in self._submitted:
                return
            self._submitted.add(run_id)
        self._executor.submit(self._execute, run_id, request)

    def _execute(self, run_id: str, request: RunRequest) -> None:
        try:
            self.service.execute_krail_workflow(run_id, request)
        finally:
            with self._lock:
                self._submitted.discard(run_id)
