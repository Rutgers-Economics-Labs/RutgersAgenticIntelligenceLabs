from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.krail_runtime import LocalKrailRuntime, ProjectRef


FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "examples" / "krail-project"


@pytest.fixture
def runtime() -> LocalKrailRuntime:
    return LocalKrailRuntime()


@pytest.fixture
def fixture_project(tmp_path: Path) -> ProjectRef:
    destination = tmp_path / "krail-project"
    shutil.copytree(FIXTURE_ROOT, destination)
    return ProjectRef(project_id="fixture", path=destination)
