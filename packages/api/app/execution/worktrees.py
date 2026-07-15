"""Git worktree isolation and all-or-nothing batch integration for local RAIL."""
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from .errors import BaselineMismatchError, IntegrationError


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=check)


class WorktreeManager:
    """Creates private branches at a recorded baseline; safe for one process via caller lock."""

    def prepare(self, repo: Path, *, baseline: str, run_id: str, root: Path) -> Path:
        repo, root = repo.resolve(), root.resolve()
        resolved_baseline = _git(repo, "rev-parse", "--verify", f"{baseline}^{{commit}}", check=False)
        if resolved_baseline.returncode:
            raise BaselineMismatchError(f"Unknown baseline commit: {baseline}")
        destination = root / run_id
        if destination.exists():
            raise FileExistsError(destination)
        branch = f"rail/run/{run_id}"
        _git(repo, "worktree", "add", "-b", branch, str(destination), baseline)
        return destination

    def remove(self, repo: Path, worktree: Path) -> None:
        _git(repo.resolve(), "worktree", "remove", "--force", str(worktree.resolve()))


class AtomicCombiner:
    """Combines approved branch tips without changing the canonical project branch.

    Hosted/multi-node coordination and publishing the resulting commit are deferred.
    """

    def combine(self, repo: Path, *, baseline: str, candidate_commits: list[str], batch_id: str,
                validate: Callable[[Path], None] | None = None) -> str:
        repo = repo.resolve()
        resolved = _git(repo, "rev-parse", "--verify", f"{baseline}^{{commit}}", check=False)
        if resolved.returncode:
            raise BaselineMismatchError(f"Unknown baseline commit: {baseline}")
        baseline = resolved.stdout.strip()
        if not candidate_commits:
            raise IntegrationError("At least one candidate commit is required")
        if len(candidate_commits) != len(set(candidate_commits)):
            raise IntegrationError("Candidate commits must be unique and ordered")
        for candidate in candidate_commits:
            verified = _git(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}", check=False)
            if verified.returncode or _git(repo, "merge-base", "--is-ancestor", baseline, candidate, check=False).returncode:
                raise BaselineMismatchError(f"Candidate {candidate} does not descend from baseline {baseline}")
        with tempfile.TemporaryDirectory(prefix="rail-integrate-") as directory:
            worktree = Path(directory) / "integration"
            branch = f"rail/integration/{batch_id}-{uuid4().hex[:8]}"
            _git(repo, "worktree", "add", "-b", branch, str(worktree), baseline)
            try:
                for candidate in candidate_commits:
                    applied = _git(worktree, "cherry-pick", "--no-commit", candidate, check=False)
                    if applied.returncode:
                        _git(worktree, "cherry-pick", "--abort", check=False)
                        raise IntegrationError(f"Cannot apply {candidate}: {applied.stderr.strip()}")
                if validate:
                    validate(worktree)
                message = f"RAIL combined batch {batch_id}\n\nBaseline: {baseline}\nCandidates: {', '.join(candidate_commits)}"
                committed = _git(worktree, "commit", "-m", message, check=False)
                if committed.returncode:
                    raise IntegrationError(f"Combined commit failed: {committed.stderr.strip()}")
                combined = _git(worktree, "rev-parse", "HEAD").stdout.strip()
                # Keep an auditable, durable ref before removing the temporary branch.
                _git(repo, "update-ref", f"refs/rail/integrations/{batch_id}", combined)
                return combined
            except Exception:
                _git(worktree, "reset", "--hard", baseline, check=False)
                raise
            finally:
                _git(repo, "worktree", "remove", "--force", str(worktree), check=False)
                _git(repo, "branch", "-D", branch, check=False)
