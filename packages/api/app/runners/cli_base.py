from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.runners.base import BaseRunner, RunnerEvent, RunnerEventType, TaskPayload

RUNNER_STATE_DIRNAME = ".runner"


def runner_runtime_paths(session_root: str) -> dict[str, Path]:
    root = Path(session_root) / RUNNER_STATE_DIRNAME
    return {
        "root": root,
        "stdout": root / "stdout.log",
        "stderr": root / "stderr.log",
        "exit_code": root / "exit_code.txt",
        "pid": root / "pid.txt",
        "command": root / "command.json",
    }


@dataclass
class LocalCliSession:
    session_id: str
    command: list[str]
    cwd: str | None
    prompt: str
    process: asyncio.subprocess.Process | None = None
    status: str = "queued"
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)
    events: list[RunnerEvent] = field(default_factory=list)
    returncode: int | None = None
    session_root: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    pid: int | None = None


class LocalCLIRunner(BaseRunner):
    runner_name: str = "cli"
    command: str = ""
    prompt_flag: str = "-p"
    description_text: str = ""

    def __init__(self, command: str | None = None) -> None:
        self._command = (command or self.command or "").strip()
        self._sessions: dict[str, LocalCliSession] = {}

    @property
    def name(self) -> str:
        return self.runner_name

    @property
    def description(self) -> str:
        return self.description_text

    def _ensure_available(self) -> str:
        executable = shlex.split(self._command)[0] if self._command else ""
        path = shutil.which(executable) if executable else None
        if not path:
            raise RuntimeError(
                f"{self.runner_name} CLI is not available. Configure the command or install '{executable or self.runner_name}'."
            )
        return path

    def _build_prompt(self, task_payload: TaskPayload) -> str:
        allowed = "\n".join(f"- {path}" for path in task_payload.allowed_paths) or "- none declared"
        criteria = "\n".join(f"- {item}" for item in task_payload.acceptance_criteria) or "- satisfy the task request"

        sections = [
            f"Role: {task_payload.role}",
            f"Project: {task_payload.project_slug}",
            f"Task ID: {task_payload.task_id}",
            f"Bash access: {'enabled' if task_payload.bash_access else 'disabled'}",
            "",
            f"Task:\n{task_payload.task_description}",
            "",
            f"Allowed paths:\n{allowed}",
            "",
            f"Acceptance criteria:\n{criteria}",
        ]

        if task_payload.project_context:
            sections.append("")
            sections.append("Project context:")
            sections.append(task_payload.project_context)

        if task_payload.allowed_secrets:
            secret_names = "\n".join(f"- {name}" for name in sorted(task_payload.allowed_secrets))
            sections.extend(
                [
                    "",
                    "Available environment secrets:",
                    secret_names,
                    "Use these by reading environment variables; do not print or commit their values.",
                ]
            )

        return "\n".join(sections) + "\n"

    def _base_command_parts(self) -> list[str]:
        return shlex.split(self._command)

    def _find_detached_session_root(self, session_id: str) -> Path | None:
        search_root = Path.cwd()
        sessions_root = search_root / "research_plan" / "sessions"
        if not sessions_root.exists():
            return None
        for command_file in sessions_root.glob("*/*/.runner/command.json"):
            try:
                payload = json.loads(command_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(payload.get("session_id") or "") == session_id:
                return command_file.parent.parent
        return None

    def _detached_session_snapshot(self, session_id: str) -> dict[str, Any] | None:
        root = self._find_detached_session_root(session_id)
        if root is None:
            return None
        runtime_paths = runner_runtime_paths(str(root))
        try:
            command = json.loads(runtime_paths["command"].read_text(encoding="utf-8"))
        except Exception:
            command = {}
        try:
            from app.services import session_files

            state = session_files.read_state(root)
            file_events = session_files.list_events(root)
        except Exception:
            state = {}
            file_events = []

        def _tail_lines(path: Path, limit: int = 50) -> list[str]:
            if not path.exists():
                return []
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]

        stdout_lines = _tail_lines(runtime_paths["stdout"])
        stderr_lines = _tail_lines(runtime_paths["stderr"])
        return {
            "root": root,
            "runtime_paths": runtime_paths,
            "command": command,
            "state": state,
            "file_events": file_events,
            "stdout_lines": stdout_lines,
            "stderr_lines": stderr_lines,
        }

    def _runner_events_from_file_events(self, session_id: str, file_events: list[dict[str, Any]]) -> list[RunnerEvent]:
        event_type_map = {
            "session_started": RunnerEventType.SESSION_CREATED,
            "status_changed": RunnerEventType.STATUS_CHANGED,
            "approval_requested": RunnerEventType.APPROVAL_REQUESTED,
            "question_asked": RunnerEventType.QUESTION_ASKED,
            "assistant_message": RunnerEventType.PROGRESS,
            "tool_call": RunnerEventType.BASH_COMMAND_STARTED,
            "tool_result": RunnerEventType.BASH_COMMAND_COMPLETED,
            "file_change_detected": RunnerEventType.FILE_CHANGE_DETECTED,
            "verification_started": RunnerEventType.VERIFICATION_STARTED,
            "verification_completed": RunnerEventType.VERIFICATION_COMPLETED,
            "completed": RunnerEventType.COMPLETED,
            "failed": RunnerEventType.FAILED,
            "cancelled": RunnerEventType.CANCELLED,
        }
        events: list[RunnerEvent] = []
        for item in file_events:
            mapped = event_type_map.get(str(item.get("type") or ""))
            if mapped is None:
                continue
            payload = {
                key: value
                for key, value in item.items()
                if key not in {"id", "timestamp", "type"}
            }
            events.append(
                RunnerEvent(
                    event_type=mapped,
                    session_id=session_id,
                    normalized_payload=payload,
                    raw_payload=dict(item),
                    debug_visibility=bool(item.get("debug_visibility", False)),
                )
            )
        return events

    def _command_args(self, prompt: str, task_payload: TaskPayload) -> list[str]:
        parts = shlex.split(self._command)
        return [*parts, self.prompt_flag, prompt]

    def _derived_events_from_stdout_line(self, session_id: str, text: str) -> list[RunnerEvent]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, dict):
            return []

        if payload.get("type") == "turn.completed":
            return [
                RunnerEvent(
                    event_type=RunnerEventType.COMPLETED,
                    session_id=session_id,
                    normalized_payload={"status": "completed"},
                    raw_payload=payload,
                )
            ]

        cursor_events = self._derived_events_from_cursor_payload(session_id, payload)
        if cursor_events:
            return cursor_events

        gemini_events = self._derived_events_from_gemini_payload(session_id, payload)
        if gemini_events:
            return gemini_events

        item = payload.get("item")
        if not isinstance(item, dict):
            return self._derived_events_from_message_payload(session_id, payload)

        events: list[RunnerEvent] = []
        item_type = item.get("type")
        event_type = payload.get("type")

        if item_type == "agent_message":
            message = item.get("text") or item.get("message")
            if message:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": message},
                        raw_payload=payload,
                    )
                )
        elif item_type == "file_change":
            for change in item.get("changes") or []:
                path = change.get("path")
                if path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={
                                "path": path,
                                "kind": change.get("kind"),
                            },
                            raw_payload=payload,
                        )
                    )
        elif item_type == "command_execution":
            normalized = {
                "command": item.get("command"),
                "aggregated_output": item.get("aggregated_output"),
                "exit_code": item.get("exit_code"),
            }
            if event_type == "item.started":
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.BASH_COMMAND_STARTED,
                        session_id=session_id,
                        normalized_payload=normalized,
                        raw_payload=payload,
                    )
                )
            elif event_type == "item.completed":
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.BASH_COMMAND_COMPLETED,
                        session_id=session_id,
                        normalized_payload=normalized,
                        raw_payload=payload,
                    )
                )
        return events

    def _derived_events_from_message_payload(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> list[RunnerEvent]:
        events: list[RunnerEvent] = []
        payload_type = payload.get("type")

        if payload_type == "assistant":
            message = payload.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text = block.get("text")
                    if text:
                        events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.PROGRESS,
                                session_id=session_id,
                                normalized_payload={"message": text},
                                raw_payload=payload,
                            )
                        )
                elif block_type == "tool_use":
                    tool_name = block.get("name")
                    tool_input = block.get("input") or {}
                    if tool_name == "Read" and tool_input.get("file_path"):
                        events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.PROGRESS,
                                session_id=session_id,
                                normalized_payload={
                                    "message": f"Reading {tool_input.get('file_path')}",
                                    "path": tool_input.get("file_path"),
                                },
                                raw_payload=payload,
                            )
                        )
                    elif tool_name in {"Write", "Edit", "NotebookEdit"} and tool_input.get("file_path"):
                        events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                                session_id=session_id,
                                normalized_payload={
                                    "path": tool_input.get("file_path"),
                                    "kind": tool_name.lower(),
                                },
                                raw_payload=payload,
                            )
                        )
                    elif tool_name == "Bash":
                        command = tool_input.get("command")
                        if command:
                            events.append(
                                RunnerEvent(
                                    event_type=RunnerEventType.BASH_COMMAND_STARTED,
                                    session_id=session_id,
                                    normalized_payload={"command": command},
                                    raw_payload=payload,
                                )
                            )
        elif payload_type == "result":
            if payload.get("subtype") == "success":
                result = payload.get("result")
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": result} if result else {},
                        raw_payload=payload,
                    )
                )
        return events

    def _derived_events_from_cursor_payload(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> list[RunnerEvent]:
        events: list[RunnerEvent] = []
        payload_type = payload.get("type")

        if payload_type == "assistant":
            message = payload.get("message") or {}
            for block in message.get("content") or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text")
                    if text:
                        events.append(
                            RunnerEvent(
                                event_type=RunnerEventType.PROGRESS,
                                session_id=session_id,
                                normalized_payload={"message": text},
                                raw_payload=payload,
                            )
                        )
            return events

        if payload_type == "thinking" and payload.get("subtype") == "delta":
            text = payload.get("text")
            if text:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": text},
                        raw_payload=payload,
                    )
                )
            return events

        if payload_type == "tool_call":
            subtype = payload.get("subtype")
            tool_call = payload.get("tool_call") or {}

            if "readToolCall" in tool_call:
                args = (tool_call.get("readToolCall") or {}).get("args") or {}
                path = args.get("path")
                if path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={
                                "message": f"Reading {path}",
                                "path": path,
                            },
                            raw_payload=payload,
                        )
                    )
                return events

            if "editToolCall" in tool_call:
                edit = tool_call.get("editToolCall") or {}
                args = edit.get("args") or {}
                result = edit.get("result") or {}
                path = args.get("path") or (result.get("success") or {}).get("path")
                stream_content = args.get("streamContent")
                if subtype == "started" and stream_content:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={
                                "message": f"Editing {path}" if path else "Editing file",
                                "path": path,
                            },
                            raw_payload=payload,
                        )
                    )
                if path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={"path": path, "kind": "edit"},
                            raw_payload=payload,
                        )
                    )
                return events

        if payload_type == "result" and not payload.get("is_error"):
            result = payload.get("result")
            if result:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": result},
                        raw_payload=payload,
                    )
                )
            return events

        return []

    def _derived_events_from_gemini_payload(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> list[RunnerEvent]:
        events: list[RunnerEvent] = []
        payload_type = payload.get("type")

        if payload_type == "tool_use":
            tool_name = payload.get("tool_name")
            parameters = payload.get("parameters") or {}
            if tool_name == "update_topic":
                summary = parameters.get("summary") or parameters.get("strategic_intent") or parameters.get("title")
                if summary:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={"message": summary},
                            raw_payload=payload,
                        )
                    )
            elif tool_name == "read_file":
                file_path = parameters.get("file_path")
                if file_path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.PROGRESS,
                            session_id=session_id,
                            normalized_payload={
                                "message": f"Reading {file_path}",
                                "path": file_path,
                            },
                            raw_payload=payload,
                        )
                    )
            elif tool_name == "write_file":
                file_path = parameters.get("file_path")
                if file_path:
                    events.append(
                        RunnerEvent(
                            event_type=RunnerEventType.FILE_CHANGE_DETECTED,
                            session_id=session_id,
                            normalized_payload={"path": file_path, "kind": "write"},
                            raw_payload=payload,
                        )
                    )
            return events

        if payload_type == "message" and payload.get("role") == "assistant":
            content = payload.get("content")
            if content:
                events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.PROGRESS,
                        session_id=session_id,
                        normalized_payload={"message": content},
                        raw_payload=payload,
                    )
                )
            return events

        if payload_type == "result" and payload.get("status") == "success":
            events.append(
                RunnerEvent(
                    event_type=RunnerEventType.COMPLETED,
                    session_id=session_id,
                    normalized_payload={"status": "completed"},
                    raw_payload=payload,
                )
            )
            return events

        return []

    async def _consume_stream(
        self,
        session: LocalCliSession,
        stream: asyncio.StreamReader | None,
        *,
        stderr: bool,
    ) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if stderr:
                session.stderr_lines.append(text)
            else:
                session.stdout_lines.append(text)
            session.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.PROGRESS,
                    session_id=session.session_id,
                    normalized_payload={
                        "stream": "stderr" if stderr else "stdout",
                        "line": text,
                    },
                    raw_payload={"line": text},
                    debug_visibility=False,
                )
            )
            if not stderr:
                derived = self._derived_events_from_stdout_line(session.session_id, text)
                session.events.extend(derived)
                for ev in derived:
                    self._persist_event(session, ev)

    def _persist_event(self, session: LocalCliSession, event: RunnerEvent) -> None:
        if not session.session_root:
            return
        from pathlib import Path
        from app.services import session_files
        root = Path(session.session_root)
        if root.exists():
            event_type_map = {
                RunnerEventType.PROGRESS: "assistant_message",
                RunnerEventType.BASH_COMMAND_STARTED: "tool_call",
                RunnerEventType.BASH_COMMAND_COMPLETED: "tool_result",
                RunnerEventType.FILE_CHANGE_DETECTED: "file_change_detected",
                RunnerEventType.COMPLETED: "completed",
                RunnerEventType.FAILED: "failed",
                RunnerEventType.CANCELLED: "cancelled",
                RunnerEventType.STATUS_CHANGED: "status_changed",
                RunnerEventType.APPROVAL_REQUESTED: "approval_requested",
                RunnerEventType.QUESTION_ASKED: "question_asked",
                RunnerEventType.VERIFICATION_STARTED: "verification_started",
                RunnerEventType.VERIFICATION_COMPLETED: "verification_completed",
            }
            status_map = {
                RunnerEventType.COMPLETED: "completed",
                RunnerEventType.FAILED: "failed",
                RunnerEventType.CANCELLED: "cancelled",
                RunnerEventType.STATUS_CHANGED: event.normalized_payload.get("status"),
            }
            normalized_payload = dict(event.normalized_payload)
            explicit_status = status_map.get(event.event_type)
            normalized_payload.pop("status", None)
            session_files.append_event(
                root,
                event_type_map.get(event.event_type, event.event_type.value),
                content=normalized_payload.get("message") or normalized_payload.get("line") or normalized_payload.get("command") or "",
                status=explicit_status,
                **normalized_payload
            )

    async def _run_session(self, session: LocalCliSession) -> None:
        try:
            session.status = "running"
            session.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.STATUS_CHANGED,
                    session_id=session.session_id,
                    normalized_payload={"status": "running"},
                )
            )
            self._persist_event(session, session.events[-1])
            session.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.BASH_COMMAND_STARTED,
                    session_id=session.session_id,
                    normalized_payload={
                        "command": session.command,
                        "cwd": session.cwd,
                    },
                )
            )
            self._persist_event(session, session.events[-1])
            process = await asyncio.create_subprocess_exec(
                *session.command,
                cwd=session.cwd,
                env={**os.environ, **session.env},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            session.process = process
            await asyncio.gather(
                self._consume_stream(session, process.stdout, stderr=False),
                self._consume_stream(session, process.stderr, stderr=True),
            )
            session.returncode = await process.wait()
            if session.returncode == 0:
                session.status = "completed"
                session.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.BASH_COMMAND_COMPLETED,
                        session_id=session.session_id,
                        normalized_payload={"returncode": session.returncode},
                    )
                )
                session.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.COMPLETED,
                        session_id=session.session_id,
                        normalized_payload={"returncode": session.returncode},
                    )
                )
                self._persist_event(session, session.events[-2])
                self._persist_event(session, session.events[-1])
            else:
                session.status = "failed"
                session.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.BASH_COMMAND_COMPLETED,
                        session_id=session.session_id,
                        normalized_payload={"returncode": session.returncode},
                    )
                )
                session.events.append(
                    RunnerEvent(
                        event_type=RunnerEventType.FAILED,
                        session_id=session.session_id,
                        normalized_payload={
                            "returncode": session.returncode,
                            "stderr": "\n".join(session.stderr_lines[-20:]),
                        },
                    )
                )
                self._persist_event(session, session.events[-2])
                self._persist_event(session, session.events[-1])
        except Exception as exc:
            session.status = "failed"
            failed_event = RunnerEvent(
                event_type=RunnerEventType.FAILED,
                session_id=session.session_id,
                normalized_payload={"error": str(exc)},
                raw_payload={"error": str(exc)},
            )
            session.events.append(failed_event)
            self._persist_event(session, failed_event)

    async def create_session(self, task_payload: TaskPayload) -> dict[str, Any]:
        self._ensure_available()
        prompt = self._build_prompt(task_payload)
        session_id = f"{self.runner_name}_{uuid.uuid4().hex[:12]}"
        if not task_payload.session_root:
            raise RuntimeError(f"{self.runner_name} runner requires a session_root")
        session = LocalCliSession(
            session_id=session_id,
            command=self._command_args(prompt, task_payload),
            cwd=task_payload.local_repo_path,
            prompt=prompt,
            session_root=task_payload.session_root,
            env=dict(task_payload.allowed_secrets),
        )
        runtime_paths = runner_runtime_paths(task_payload.session_root)
        runtime_paths["root"].mkdir(parents=True, exist_ok=True)
        for key in ("stdout", "stderr"):
            runtime_paths[key].write_text("", encoding="utf-8")
        for key in ("exit_code", "pid"):
            if runtime_paths[key].exists():
                runtime_paths[key].unlink()
        runtime_paths["command"].write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "runner": self.runner_name,
                    "command": session.command,
                    "cwd": session.cwd,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        stdout_handle = runtime_paths["stdout"].open("a", encoding="utf-8")
        stderr_handle = runtime_paths["stderr"].open("a", encoding="utf-8")
        wrapped_command = (
            f"{shlex.join(session.command)}; "
            f"rc=$?; printf '%s\\n' \"$rc\" > {shlex.quote(str(runtime_paths['exit_code']))}; "
            "exit $rc"
        )
        process = subprocess.Popen(  # noqa: S602
            ["/bin/sh", "-lc", wrapped_command],
            cwd=session.cwd,
            env={**os.environ, **session.env},
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            start_new_session=True,
        )
        stdout_handle.close()
        stderr_handle.close()
        session.pid = process.pid
        runtime_paths["pid"].write_text(f"{process.pid}\n", encoding="utf-8")
        self._sessions[session_id] = session
        return {
            "session_id": session_id,
            "status": "running",
            "url": None,
            "raw": {
                "command": session.command,
                "cwd": session.cwd,
                "pid": process.pid,
            },
        }

    async def get_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            detached = self._detached_session_snapshot(session_id)
            if detached is None:
                raise ValueError(f"Unknown session: {session_id}")
            state = detached["state"]
            status = str(state.get("status") or "running")
            normalized_status = {
                "completed": RunnerEventType.COMPLETED.value,
                "failed": RunnerEventType.FAILED.value,
                "cancelled": RunnerEventType.CANCELLED.value,
            }.get(status, RunnerEventType.PROGRESS.value)
            command = detached["command"]
            return {
                "session_id": session_id,
                "status": status,
                "normalized_status": normalized_status,
                "stdout": "\n".join(detached["stdout_lines"]),
                "stderr": "\n".join(detached["stderr_lines"]),
                "raw": {
                    "command": command.get("command"),
                    "cwd": command.get("cwd"),
                    "session_root": str(detached["root"]),
                },
            }
        normalized_status = {
            "completed": RunnerEventType.COMPLETED.value,
            "failed": RunnerEventType.FAILED.value,
            "cancelled": RunnerEventType.CANCELLED.value,
        }.get(session.status, RunnerEventType.PROGRESS.value)
        return {
            "session_id": session_id,
            "status": session.status,
            "normalized_status": normalized_status,
            "stdout": "\n".join(session.stdout_lines[-50:]),
            "stderr": "\n".join(session.stderr_lines[-50:]),
            "raw": {
                "command": session.command,
                "cwd": session.cwd,
                "returncode": session.returncode,
            },
        }

    async def list_events(self, session_id: str) -> list[RunnerEvent]:
        session = self._sessions.get(session_id)
        if not session:
            detached = self._detached_session_snapshot(session_id)
            if detached is None:
                raise ValueError(f"Unknown session: {session_id}")
            return self._runner_events_from_file_events(session_id, detached["file_events"])
        return list(session.events)

    async def send_message(self, session_id: str, message: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            # Detached local CLI runners do not support true interactive follow-up
            # after launch. After an API restart the in-memory session map is empty,
            # but the file-backed session and process may still be alive. Treat
            # follow-up messages as a no-op instead of surfacing a misleading
            # "Unknown session" error back to the control plane.
            return
        session.events.append(
            RunnerEvent(
                event_type=RunnerEventType.QUESTION_ASKED,
                session_id=session_id,
                normalized_payload={"message": message, "note": "CLI runner does not support interactive follow-up after launch."},
                debug_visibility=True,
            )
        )

    async def approve(self, session_id: str, payload: dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if not session:
            # See send_message(): detached local CLI sessions are file-backed and
            # may outlive the API process that launched them. Approval nudges are
            # likewise a no-op for these runners after launch.
            return
        session.events.append(
            RunnerEvent(
                event_type=RunnerEventType.APPROVAL_REQUESTED,
                session_id=session_id,
                normalized_payload={"message": payload.get("message") or "approved"},
                debug_visibility=True,
            )
        )

    async def cancel(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Unknown session: {session_id}")
        if session.process and session.process.returncode is None:
            session.process.terminate()
        session.status = "cancelled"
        session.events.append(
            RunnerEvent(
                event_type=RunnerEventType.CANCELLED,
                session_id=session_id,
                normalized_payload={"reason": "user_requested"},
            )
        )
