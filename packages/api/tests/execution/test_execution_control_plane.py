from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from threading import Event

import pytest

from app.execution import AtomicCombiner, BaselineMismatchError, CommandExecutor, ExecutionService, FilesystemMode, InMemoryRunStore, IntegrationError, JsonRunStore, PermissionDeniedError, PermissionProfile, RunStatus, WorktreeManager
from app.krail_runtime.contracts import RunHandle, RunRequest


def profile(root: Path, **changes) -> PermissionProfile:
    values = dict(name="test", allowed_commands=frozenset({Path(sys.executable).name, "git"}), filesystem_roots=(root,), filesystem_mode=FilesystemMode.READ_WRITE, environment_allowlist=frozenset({"SAFE"}), process_enabled=True, timeout_seconds=0.2)
    values.update(changes)
    return PermissionProfile(**values)


def test_command_is_argv_only_and_profiles_gate_commands_and_shell(tmp_path: Path) -> None:
    executor = CommandExecutor(); p = profile(tmp_path)
    result = executor.run([sys.executable, "-c", "print('ok')", "; echo injected"], cwd=tmp_path, profile=p)
    assert result.stdout.strip() == "ok"
    with pytest.raises(PermissionDeniedError, match="not allowed"):
        executor.run(["echo", "no"], cwd=tmp_path, profile=p)
    with pytest.raises(PermissionDeniedError, match="Shell"):
        executor.run(["echo", "no"], cwd=tmp_path, profile=p, shell=True)


def test_path_traversal_symlink_timeout_and_cancellation_are_bounded(tmp_path: Path) -> None:
    executor = CommandExecutor(); outside = tmp_path.parent / "outside"; outside.mkdir(exist_ok=True)
    link = tmp_path / "escape"; link.symlink_to(outside, target_is_directory=True); p = profile(tmp_path)
    with pytest.raises(PermissionDeniedError, match="outside"):
        executor.run([sys.executable, "-c", "print(1)"], cwd=link, profile=p)
    assert executor.run([sys.executable, "-c", "import time; time.sleep(1)"], cwd=tmp_path, profile=p).timed_out
    cancelled = Event(); cancelled.set()
    assert executor.run([sys.executable, "-c", "print(1)"], cwd=tmp_path, profile=p, cancel=cancelled).cancelled


def test_lifecycle_events_are_durable_and_transitions_checked(tmp_path: Path) -> None:
    store_path = tmp_path / "runs.json"; service = ExecutionService(JsonRunStore(store_path))
    run = service.create_run(project_id="p", project_path=tmp_path, kind="command", profile=profile(tmp_path))
    service.transition(run.run_id, RunStatus.RUNNING); done = service.transition(run.run_id, RunStatus.SUCCEEDED, result={"code": 0})
    assert done.status is RunStatus.SUCCEEDED
    assert [event.kind for event in JsonRunStore(store_path).events(run.run_id)] == ["queued", "running", "succeeded"]
    with pytest.raises(Exception, match="Cannot transition"):
        service.transition(run.run_id, RunStatus.RUNNING)


def test_profile_concurrency_limit_is_enforced(tmp_path: Path) -> None:
    service = ExecutionService(InMemoryRunStore()); p = profile(tmp_path, max_concurrency=1)
    first = service.create_run(project_id="p", project_path=tmp_path, kind="command", profile=p)
    second = service.create_run(project_id="p", project_path=tmp_path, kind="command", profile=p)
    service.transition(first.run_id, RunStatus.RUNNING)
    with pytest.raises(Exception, match="Concurrency limit"):
        service.transition(second.run_id, RunStatus.RUNNING)
    service.cancel(first.run_id)
    assert service.transition(second.run_id, RunStatus.RUNNING).status is RunStatus.RUNNING


class FakeRuntime:
    def execute_workflow(self, project, request):
        assert request.dry_run is True
        return RunHandle(run_id="krail-1", workflow_id=request.workflow_id, status="succeeded")


def test_workflow_delegates_to_canonical_runtime(tmp_path: Path) -> None:
    service = ExecutionService(InMemoryRunStore(), FakeRuntime())
    run = service.create_run(project_id="p", project_path=tmp_path, kind="workflow", profile=profile(tmp_path), workflow_id="w")
    outcome = service.execute_krail_workflow(run.run_id, RunRequest(workflow_id="w", dry_run=True))
    assert outcome.status is RunStatus.SUCCEEDED and outcome.result["run_id"] == "krail-1"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"; repo.mkdir(); git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid"); git(repo, "config", "user.name", "Test")
    (repo / "base.txt").write_text("base\n"); git(repo, "add", "."); git(repo, "commit", "-m", "base")
    return repo


def commit_change(repo: Path, name: str) -> str:
    (repo / name).write_text(name); git(repo, "add", name); git(repo, "commit", "-m", name)
    return git(repo, "rev-parse", "HEAD")


def assert_files(worktree: Path, *names: str) -> None:
    assert all((worktree / name).is_file() for name in names)


def test_isolated_worktrees_and_atomic_combine_retains_result(repository: Path, tmp_path: Path) -> None:
    baseline = git(repository, "rev-parse", "HEAD"); manager = WorktreeManager()
    a = manager.prepare(repository, baseline=baseline, run_id="a", root=tmp_path / "trees")
    b = manager.prepare(repository, baseline=baseline, run_id="b", root=tmp_path / "trees")
    a_commit, b_commit = commit_change(a, "a.txt"), commit_change(b, "b.txt")
    combined = AtomicCombiner().combine(repository, baseline=baseline, candidate_commits=[a_commit, b_commit], batch_id="batch-1", validate=lambda wt: assert_files(wt, "a.txt", "b.txt"))
    assert git(repository, "rev-parse", "refs/rail/integrations/batch-1") == combined
    assert git(repository, "rev-parse", "main") == baseline
    manager.remove(repository, a); manager.remove(repository, b)


def test_baseline_mismatch_and_failed_validation_do_not_publish(repository: Path, tmp_path: Path) -> None:
    baseline = git(repository, "rev-parse", "HEAD"); candidate = commit_change(repository, "candidate.txt"); combiner = AtomicCombiner()
    with pytest.raises(BaselineMismatchError): combiner.combine(repository, baseline="deadbeef", candidate_commits=[candidate], batch_id="bad")
    with pytest.raises(IntegrationError): combiner.combine(repository, baseline=baseline, candidate_commits=[candidate, candidate], batch_id="duplicate")
    with pytest.raises(RuntimeError, match="validation"):
        combiner.combine(repository, baseline=baseline, candidate_commits=[candidate], batch_id="rollback", validate=lambda _: (_ for _ in ()).throw(RuntimeError("validation failed")))
    assert subprocess.run(["git", "-C", str(repository), "rev-parse", "--verify", "refs/rail/integrations/rollback"], capture_output=True).returncode != 0
    assert git(repository, "rev-parse", "main") == candidate
