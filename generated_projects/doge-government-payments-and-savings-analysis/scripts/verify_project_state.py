#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_LEDGERS = [
    "research_plan/current_plan.md",
    "research_plan/task_board.md",
    "research_plan/assumptions.md",
    "research_plan/target_state.md",
    "research_plan/source_registry.md",
    "research_plan/data_gaps.md",
]

PLACEHOLDER_MARKERS = [
    "example.com",
    "review-required",
    "missing_auth_or_manual",
]

REQUIRED_PROJECT_FILES = [
    "topics/brief.md",
    "topics/source_notes.md",
    "specs/research_question.yaml",
    "specs/ontology_scope.md",
    ".ontology/ontology.yaml",
    ".ontology/pipelines/doge-government-payments-and-savings-analysis-pipeline.yaml",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def require_ledgers(failures: list[str]) -> None:
    for rel in REQUIRED_LEDGERS:
        path = ROOT / rel
        if not path.exists() or not read_text(path).strip():
            fail(f"Missing or empty required ledger: {rel}", failures)


def require_project_files(failures: list[str]) -> None:
    for rel in REQUIRED_PROJECT_FILES:
        path = ROOT / rel
        if not path.exists() or not read_text(path).strip():
            fail(f"Missing or empty required project file: {rel}", failures)


def check_sources(failures: list[str]) -> None:
    for path in sorted((ROOT / ".ontology" / "sources").glob("*.yaml")):
        raw = read_text(path)
        lowered = raw.lower()
        for marker in PLACEHOLDER_MARKERS:
            if marker in lowered:
                fail(f"Placeholder or review-only ontology source: {path.relative_to(ROOT)} ({marker})", failures)
                break
        try:
            data = yaml.safe_load(raw) or {}
        except Exception as exc:
            fail(f"Invalid source YAML: {path.relative_to(ROOT)} ({exc})", failures)
            continue
        if not isinstance(data, dict):
            fail(f"Source config root must be a mapping: {path.relative_to(ROOT)}", failures)
            continue
        if not (data.get("url") or data.get("path")):
            fail(f"Source config missing url/path: {path.relative_to(ROOT)}", failures)
        fields = data.get("fields")
        if not isinstance(fields, list) or not fields:
            fail(f"Source config missing field mappings: {path.relative_to(ROOT)}", failures)

        description = str(data.get("description", "")).lower()
        if "readiness: ready" not in description and "readiness: draft_for_review" not in description:
            fail(f"Source config missing readiness marker: {path.relative_to(ROOT)}", failures)

def check_research_question(failures: list[str]) -> None:
    path = ROOT / "specs" / "research_question.yaml"
    try:
        data = yaml.safe_load(read_text(path)) or {}
    except Exception as exc:
        fail(f"Invalid research question YAML: {exc}", failures)
        return
    for key in ("title", "objective", "methods", "deliverables"):
        if not data.get(key):
            fail(f"Research question missing required field: {key}", failures)


def check_ontology_scope_alignment(failures: list[str]) -> None:
    ontology = read_text(ROOT / ".ontology" / "ontology.yaml")
    scope = read_text(ROOT / "specs" / "ontology_scope.md")
    for token in ("PaymentRecord", "PaymentStatisticsBucket", "SavingsRecord"):
        if token not in ontology:
            fail(f"Ontology missing core class: {token}", failures)
        if token not in scope:
            fail(f"Ontology scope plan missing core class: {token}", failures)


def main() -> int:
    failures: list[str] = []
    require_ledgers(failures)
    require_project_files(failures)
    check_sources(failures)
    check_research_question(failures)
    check_ontology_scope_alignment(failures)

    if failures:
        print("VERIFICATION FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
