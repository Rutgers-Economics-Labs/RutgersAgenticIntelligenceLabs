from __future__ import annotations

import asyncio
import json
import os
import signal
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
        """Construct the prompt for the runner based on task type."""
        from app.runners.context_compilers.base import get_compiler
        from app.runners.contracts import TaskType
        
        # Determine task type from role
        task_type = TaskType.ANALYSIS
        if task_payload.role == "data":
            task_type = TaskType.DATA_INGESTION
        elif task_payload.role == "artifact":
            task_type = TaskType.ARTIFACT_WRITING
            
        compiler = get_compiler(task_type)
        return compiler.compile(task_payload)

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
        """Parse runner-specific stdout into normalized RunnerEvents."""
        from app.runners.event_normalizers.base import get_normalizer
        
        normalizer = get_normalizer(self.runner_name)
        return normalizer.normalize_line(session_id, text)

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
        
        # Phase 3: Inject RAIL environment variables and MCP config
        from app.runners.mcp_injector import inject_mcp_config
        from pathlib import Path
        
        workspace_root = Path(task_payload.local_repo_path) if task_payload.local_repo_path else Path(task_payload.session_root)
        
        inject_mcp_config(
            workspace_root,
            project_slug=task_payload.project_slug,
            session_id=session_id,
            work_order_id=task_payload.work_order_id,
            local_mode=True, # default to local mode for CLI runners
        )

        env = dict(task_payload.allowed_secrets)
        env["RAIL_PROJECT"] = task_payload.project_slug
        env["RAIL_SESSION_ID"] = session_id
        if task_payload.work_order_id:
            env["RAIL_WORK_ORDER_ID"] = task_payload.work_order_id
        if task_payload.work_order_path:
            env["RAIL_WORK_ORDER_PATH"] = task_payload.work_order_path

        session = LocalCliSession(
            session_id=session_id,
            command=self._command_args(prompt, task_payload),
            cwd=task_payload.local_repo_path,
            prompt=prompt,
            session_root=task_payload.session_root,
            env=env,
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
            detached = self._detached_session_snapshot(session_id)
            if detached is None:
                raise ValueError(f"Unknown session: {session_id}")
            runtime_paths = detached["runtime_paths"]
            pid = None
            if runtime_paths["pid"].exists():
                try:
                    pid = int(runtime_paths["pid"].read_text(encoding="utf-8").strip() or "0")
                except ValueError:
                    pid = None
            if pid and pid > 0:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    pass
            try:
                from app.services import session_files

                session_files.append_event(
                    detached["root"],
                    "cancelled",
                    content="Session cancelled by user.",
                    status="cancelled",
                )
                session_files.update_state(detached["root"], status="cancelled", review_status="needs_changes")
            except Exception:
                pass
            return
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
