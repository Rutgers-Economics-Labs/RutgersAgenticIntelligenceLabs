from __future__ import annotations

import asyncio
import json
import shlex
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.runners.base import BaseRunner, RunnerEvent, RunnerEventType, TaskPayload


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

        return "\n".join(sections) + "\n"

    def _base_command_parts(self) -> list[str]:
        return shlex.split(self._command)

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

        item = payload.get("item")
        if not isinstance(item, dict):
            return []

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
            session_files.append_event(
                root,
                event.event_type.value,
                content=event.normalized_payload.get("message") or event.normalized_payload.get("line") or "",
                **event.normalized_payload
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
            session.events.append(
                RunnerEvent(
                    event_type=RunnerEventType.FAILED,
                    session_id=session.session_id,
                    normalized_payload={"error": str(exc)},
                    raw_payload={"error": str(exc)},
                )
            )

    async def create_session(self, task_payload: TaskPayload) -> dict[str, Any]:
        self._ensure_available()
        prompt = self._build_prompt(task_payload)
        session_id = f"{self.runner_name}_{uuid.uuid4().hex[:12]}"
        session = LocalCliSession(
            session_id=session_id,
            command=self._command_args(prompt, task_payload),
            cwd=task_payload.local_repo_path,
            prompt=prompt,
            session_root=task_payload.session_root,
        )
        session.events.append(
            RunnerEvent(
                event_type=RunnerEventType.SESSION_CREATED,
                session_id=session_id,
                normalized_payload={"runner": self.runner_name},
            )
        )
        self._sessions[session_id] = session
        asyncio.create_task(self._run_session(session))
        return {
            "session_id": session_id,
            "status": "running",
            "url": None,
            "raw": {
                "command": session.command,
                "cwd": session.cwd,
            },
        }

    async def get_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Unknown session: {session_id}")
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
            raise ValueError(f"Unknown session: {session_id}")
        return list(session.events)

    async def send_message(self, session_id: str, message: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Unknown session: {session_id}")
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
            raise ValueError(f"Unknown session: {session_id}")
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
