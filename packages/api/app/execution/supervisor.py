"""Bounded, single-node background execution supervisor.

Workers are intentionally process-local. Restart reconciliation is performed by
ExecutionService; distributed scheduling/locking is deferred to a future service.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock

from app.krail_runtime.contracts import RunRequest

from .service import ExecutionService
from .models import RunStatus, TERMINAL_STATUSES


class LocalRunSupervisor:
    def __init__(self, service: ExecutionService, *, max_workers: int = 4) -> None:
        self.service = service
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="krail-run")
        self._submitted: set[str] = set()
        self._futures: dict[str, Future[None]] = {}
        self._lock = RLock()

    def submit_workflow(self, run_id: str, request: RunRequest) -> None:
        with self._lock:
            if run_id in self._submitted:
                return
            self._submitted.add(run_id)
        try:
            future = self._executor.submit(self._execute, run_id, request)
        except Exception:
            with self._lock:
                self._submitted.discard(run_id)
            self._fail_safely(run_id)
            raise
        with self._lock:
            self._futures[run_id] = future

    def _execute(self, run_id: str, request: RunRequest) -> None:
        try:
            # Profile limits live in ExecutionService. A larger thread pool waits
            # for capacity rather than dropping a queued run on a Future exception.
            while True:
                record = self.service.store.get(run_id)
                if record.status in TERMINAL_STATUSES:
                    return
                try:
                    self.service.execute_krail_workflow(run_id, request)
                    return
                except Exception as exc:
                    record = self.service.store.get(run_id)
                    if record.status is RunStatus.CANCELLED:
                        return
                    if record.status is RunStatus.QUEUED and "Concurrency limit reached" in str(exc):
                        if self.service.cancellation_hook(run_id).wait(0.02):
                            return
                        continue
                    self._fail_safely(run_id)
                    return
        finally:
            with self._lock:
                self._submitted.discard(run_id)
                self._futures.pop(run_id, None)

    def _fail_safely(self, run_id: str) -> None:
        try:
            record = self.service.store.get(run_id)
            if record.status not in TERMINAL_STATUSES:
                self.service.transition(run_id, RunStatus.FAILED, result={"error": "Workflow execution failed"})
        except Exception:
            # There is no safe recovery if durable operational storage is unavailable.
            pass

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        """Stop the local worker pool during application lifespan shutdown.

        Parent bootstrap must call this from lifespan cleanup. Multi-node worker
        ownership and coordinated shutdown remain explicitly out of scope.
        """
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)
