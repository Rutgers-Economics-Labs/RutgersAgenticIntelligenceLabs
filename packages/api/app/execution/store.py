"""Thread-safe, single-process operational run/event storage.

Multi-node persistence and distributed locking are deliberately deferred.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from threading import RLock

from .models import RunEvent, RunRecord


class InMemoryRunStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, RunRecord] = {}
        self._events: dict[str, list[RunEvent]] = defaultdict(list)

    def create(self, record: RunRecord) -> RunRecord:
        with self._lock:
            if record.run_id in self._records:
                raise ValueError(f"Duplicate run id: {record.run_id}")
            self._records[record.run_id] = record
            return record

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            return self._records[run_id]

    def records(self) -> list[RunRecord]:
        """Return operational records for service restart recovery."""
        with self._lock:
            return list(self._records.values())

    def replace(self, record: RunRecord) -> RunRecord:
        with self._lock:
            if record.run_id not in self._records:
                raise KeyError(record.run_id)
            self._records[record.run_id] = record
            return record

    def append_event(self, event: RunEvent) -> RunEvent:
        with self._lock:
            if event.run_id not in self._records:
                raise KeyError(event.run_id)
            self._events[event.run_id].append(event)
            return event

    def events(self, run_id: str) -> list[RunEvent]:
        with self._lock:
            return list(self._events[run_id])


class JsonRunStore(InMemoryRunStore):
    """Small durable metadata store for a single local process.

    This file contains run operational state and events only, never KRAIL records.
    Atomic rename makes each completed write visible as one snapshot. Multi-node
    locking/replication is intentionally out of scope for M4.
    """
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path.resolve()
        if self.path.exists():
            raw = json.loads(self.path.read_text())
            self._records = {item["run_id"]: RunRecord.model_validate(item) for item in raw.get("records", [])}
            self._events = defaultdict(list, {key: [RunEvent.model_validate(event) for event in value]
                                                for key, value in raw.get("events", {}).items()})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [record.model_dump(mode="json") for record in self._records.values()],
                   "events": {key: [event.model_dump(mode="json") for event in value]
                              for key, value in self._events.items()}}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True))
        temporary.replace(self.path)

    def create(self, record: RunRecord) -> RunRecord:
        with self._lock:
            result = super().create(record)
            self._save()
            return result

    def replace(self, record: RunRecord) -> RunRecord:
        with self._lock:
            result = super().replace(record)
            self._save()
            return result

    def append_event(self, event: RunEvent) -> RunEvent:
        with self._lock:
            result = super().append_event(event)
            self._save()
            return result
