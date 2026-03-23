"""
Run Python user code in a child process (stronger isolation than in-process exec).

Used when settings.execute_python_mode == \"subprocess\" and for POST /analysis/run-code
(with optional artifact upload to StorageService).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("rail.subprocess_code")

_CLI = settings.engine_root / "engine" / "code_subprocess_cli.py"


def _pythonpath_env() -> str:
    root = str(settings.engine_root)
    extra = os.environ.get("PYTHONPATH", "")
    if not extra:
        return root
    return os.pathsep.join([root, extra])


def _host_command(tmp_path: Path, user_py: Path) -> list[str]:
    return [sys.executable, str(_CLI), str(user_py)]


def _docker_command(tmp_path: Path, user_py: Path, duck_abs: Path) -> list[str]:
    """Linux/macOS: run the same CLI inside a container with bind mounts."""
    image = (settings.execute_docker_image or "").strip()
    engine_abs = settings.engine_root.resolve()
    work = "/rail_workspace"
    eng = "/rail_engine"
    duck_str = str(duck_abs)
    duck_parent = str(duck_abs.parent)
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-v",
        f"{tmp_path}:{work}",
        "-v",
        f"{duck_parent}:{duck_parent}:ro",
        "-v",
        f"{engine_abs}:{eng}:ro",
        "-w",
        work,
        "-e",
        f"RAIL_DUCKDB_PATH={duck_str}",
        "-e",
        f"RAIL_OUTPUT_DIR={work}/artifacts",
        "-e",
        f"RAIL_MANIFEST_PATH={work}/_rail_manifest.json",
        "-e",
        f"PYTHONPATH={eng}",
        image,
        "python",
        "-u",
        f"{eng}/engine/code_subprocess_cli.py",
        f"{work}/user_code.py",
    ]


async def run_user_code(
    code: str,
    timeout_seconds: int,
    *,
    upload_artifacts: bool = False,
) -> dict:
    """
    Execute `code` via code_subprocess_cli.py. Returns the same shape as code_runner.run_code,
    plus optional \"artifacts\": [{filename, storageKey}] when upload_artifacts is True.
    """
    from app.services import sql_service

    duck = sql_service.get_path()
    if duck is None or not duck.is_file():
        return {
            "stdout": "",
            "stderr": "",
            "dataframes": {},
            "figures": [],
            "error": "No DuckDB database loaded. Run a hydration pipeline first.",
            "artifacts": [],
        }

    if not _CLI.is_file():
        return {
            "stdout": "",
            "stderr": "",
            "dataframes": {},
            "figures": [],
            "error": f"Subprocess runner missing: {_CLI}",
            "artifacts": [],
        }

    run_id = f"analysis-{uuid.uuid4().hex[:12]}"
    duck_abs = duck.resolve()

    with tempfile.TemporaryDirectory(prefix="rail_code_") as tmp:
        tmp_path = Path(tmp)
        user_py = tmp_path / "user_code.py"
        user_py.write_text(code, encoding="utf-8")
        artifacts_dir = tmp_path / "artifacts"
        artifacts_dir.mkdir()
        manifest_path = tmp_path / "_rail_manifest.json"

        use_docker = bool((settings.execute_docker_image or "").strip()) and sys.platform != "win32"
        if (settings.execute_docker_image or "").strip() and sys.platform == "win32":
            logger.warning(
                "execute_docker_image is set; Docker mode is not supported on Windows. "
                "Using host Python subprocess."
            )

        if use_docker:
            cmd = _docker_command(tmp_path, user_py, duck_abs)
            child_env = {**os.environ}
        else:
            cmd = _host_command(tmp_path, user_py)
            child_env = {
                **os.environ,
                "PYTHONPATH": _pythonpath_env(),
                "RAIL_DUCKDB_PATH": str(duck_abs),
                "RAIL_OUTPUT_DIR": str(artifacts_dir.resolve()),
                "RAIL_MANIFEST_PATH": str(manifest_path.resolve()),
            }

        cwd = str(tmp_path)
        logger.info("subprocess execute: %s (cwd=%s docker=%s)", cmd, cwd, use_docker)

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "stdout": "",
                "stderr": "",
                "dataframes": {},
                "figures": [],
                "error": f"Execution timed out after {timeout_seconds}s",
                "artifacts": [],
            }

        wrapper_stderr = err_b.decode(errors="replace") if err_b else ""
        wrapper_stdout = out_b.decode(errors="replace") if out_b else ""

        manifest: dict = {}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {
                    "error": "Invalid manifest JSON from subprocess",
                    "stdout": wrapper_stdout,
                    "stderr": wrapper_stderr,
                }

        result = {
            "stdout": manifest.get("stdout", "") + (wrapper_stdout or ""),
            "stderr": manifest.get("stderr", "") + (wrapper_stderr or ""),
            "dataframes": manifest.get("dataframes") or {},
            "figures": manifest.get("figures") or [],
            "error": manifest.get("error"),
            "artifacts": [],
        }

        if upload_artifacts:
            from app.services.storage_service import storage

            uploaded: list[dict] = []
            for path in sorted(artifacts_dir.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(artifacts_dir).as_posix()
                    key = await storage.upload(run_id, rel, path)
                    uploaded.append({"filename": rel, "storageKey": key})
            result["artifacts"] = uploaded

        return result
