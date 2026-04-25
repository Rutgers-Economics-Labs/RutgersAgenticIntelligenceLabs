from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from app.runners import session_lifecycle
from app.services import session_files
from app.services.role_runtime_service import load_role_runtime_config
from rail.bootstrap import bootstrap_future_project


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Codex Test")
    _git(root, "config", "user.email", "codex@example.com")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")


def test_workspace_review_flow_runs_setup_and_verification(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Workspace Project")
    setup_script = tmp_path / "scripts" / "setup-workspace.sh"
    setup_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf 'workspace ready\\n' > \"$RAIL_WORKSPACE_ROOT/setup-ran.txt\"\n",
        encoding="utf-8",
    )
    verify_script = tmp_path / "scripts" / "run-verification.sh"
    verify_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "test -f \"$RAIL_WORKSPACE_ROOT/setup-ran.txt\"\n"
        "echo 'verification ok'\n",
        encoding="utf-8",
    )
    _init_repo(tmp_path)

    session_root = session_files.ensure_session_root(tmp_path, "coding", "sess-1")
    workspace_root, workspace_branch, workspace_config = session_lifecycle._prepare_workspace(
        tmp_path,
        "coding",
        "sess-1",
    )
    asyncio.run(
        session_lifecycle._materialize_workspace(
            project_root=tmp_path,
            workspace_root=workspace_root,
            base_branch="main",
            workspace_branch=workspace_branch,
        )
    )

    setup_result = asyncio.run(
        session_lifecycle._run_workspace_setup(
            project_root=tmp_path,
            workspace_root=workspace_root,
            session_root=session_root,
            session_id="sess-1",
            role="coding",
            base_branch="main",
            workspace_branch=workspace_branch,
            workspace_config=workspace_config,
        )
    )
    assert setup_result["status"] == "passed"
    assert (workspace_root / "setup-ran.txt").exists()

    readme = workspace_root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nworkspace change\n", encoding="utf-8")
    session_files.update_state(
        session_root,
        status="completed",
        workspace_path=str(workspace_root),
        workspace_branch=workspace_branch,
        review_status="pending",
    )
    asyncio.run(
        session_lifecycle._finalize_workspace_review(
            convex_session_id="sess-1",
            session={"role": "coding"},
            project_root=tmp_path,
            session_root=session_root,
            base_branch="main",
        )
    )

    state = session_files.read_state(session_root)
    diff_text = (session_root / "diff.md").read_text(encoding="utf-8")
    verification_text = (session_root / "verification.md").read_text(encoding="utf-8")

    assert state["verification_status"] == "passed"
    assert state["review_status"] == "review"
    assert "README.md" in diff_text
    assert "status: `passed`" in verification_text


def test_role_aliases_resolve_repo_configs(tmp_path: Path):
    bootstrap_future_project(tmp_path, name="Alias Project")

    config = load_role_runtime_config(
        {
            "_id": "project-1",
            "slug": "alias-project",
            "localRepoPath": str(tmp_path),
        },
        "researcher",
    )

    assert config.role == "research"
    assert config.config_path.name == "research.yaml"
