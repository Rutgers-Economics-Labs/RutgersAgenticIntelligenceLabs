from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

from app.services import session_files


def test_session_files_round_trip(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-1")

    first_event = session_files.append_event(
        root,
        "assistant_message",
        role="assistant",
        content="Inspecting the repo.",
        status="running",
    )
    command = session_files.append_command(
        root,
        "inject_message",
        content="Please summarize the current diff.",
    )
    session_files.mark_command_processed(root, int(command["id"]))

    state = session_files.read_state(root)
    events = session_files.list_events(root)
    commands = session_files.list_commands(root)
    summary = (root / "summary.md").read_text(encoding="utf-8")

    assert first_event["id"] == 1
    assert state["status"] == "running"
    assert len(events) == 1
    assert commands[0]["processed"] is True
    assert "Inspecting the repo." in summary


def test_session_files_skip_malformed_jsonl(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-2")
    path = root / "session.ndjson"
    path.write_text('{"id": 1, "type": "assistant_message"}\n{bad json\n', encoding="utf-8")

    events = session_files.list_events(root)

    assert len(events) == 1
    assert events[0]["type"] == "assistant_message"


def test_session_summary_includes_publish_metadata(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-publish")
    session_files.update_state(
        root,
        status="completed",
        publish_status="published",
        publish_strategy="github_app_commit",
        publish_commit_sha="abc123",
    )
    session_files.refresh_summary(root)

    summary = (root / "summary.md").read_text(encoding="utf-8")

    assert "publish_status: `published`" in summary
    assert "publish_strategy: `github_app_commit`" in summary
    assert "publish_commit_sha: `abc123`" in summary


def test_append_command_reuses_idempotency_key(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-3")

    first = session_files.append_command(
        root,
        "inject_message",
        content="hello",
        payload={"source": "test"},
        idempotency_key="same-key",
    )
    second = session_files.append_command(
        root,
        "inject_message",
        content="hello again",
        payload={"source": "test-2"},
        idempotency_key="same-key",
    )

    assert first["id"] == second["id"]
    assert len(session_files.list_commands(root)) == 1


def test_append_command_idempotency_is_atomic(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-4")
    results: list[dict] = []

    def _append() -> None:
        results.append(
            session_files.append_command(
                root,
                "approve",
                payload={"message": "ok"},
                idempotency_key="shared-key",
            )
        )

    threads = [threading.Thread(target=_append) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    commands = session_files.list_commands(root)

    assert len(commands) == 1
    assert len({item["id"] for item in results}) == 1


def test_append_event_recovers_stale_session_lock(tmp_path: Path):
    root = session_files.ensure_session_root(tmp_path, "coding", "sess-stale-lock")
    lock_path = root / ".session.lock"
    lock_path.write_text(json.dumps({"pid": 999999, "created_at": time.time() - 60}), encoding="utf-8")
    stale_time = time.time() - 60
    os.utime(lock_path, (stale_time, stale_time))

    event = session_files.append_event(
        root,
        "assistant_message",
        role="assistant",
        content="Recovered stale lock.",
        status="running",
    )

    assert event["id"] == 1
    assert not lock_path.exists()
