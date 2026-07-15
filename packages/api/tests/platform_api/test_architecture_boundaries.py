from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
APP = REPO / "packages" / "api" / "app"


def test_superseded_runtime_packages_are_absent() -> None:
    for relative in (
        "packages/engine",
        "packages/rail-py",
        "packages/mcp-server",
        "packages/api/app/services",
        "packages/api/app/routers",
        "packages/api/app/runners",
    ):
        path = REPO / relative
        restored_sources = [
            item for item in path.rglob("*")
            if item.is_file() and item.suffix in {".py", ".toml", ".yaml", ".yml"}
            and "__pycache__" not in item.parts and not item.name.endswith(".egg-info")
        ] if path.exists() else []
        assert restored_sources == [], f"legacy runtime boundary restored: {relative}"


def test_only_krail_adapter_may_reference_the_rail_python_namespace() -> None:
    violations: list[str] = []
    for source in APP.rglob("*.py"):
        if source.is_relative_to(APP / "krail_runtime"):
            continue
        text = source.read_text(encoding="utf-8")
        if "import rail" in text or "from rail" in text or 'import_module("rail")' in text:
            violations.append(str(source.relative_to(REPO)))
    assert violations == []


def test_http_routes_do_not_write_krail_project_files_directly() -> None:
    violations: list[str] = []
    for source in (APP / "api").rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        if any(token in text for token in (".write_text(", ".write_bytes(", "yaml.dump(", "yaml.safe_dump(")):
            violations.append(str(source.relative_to(REPO)))
    assert violations == []
