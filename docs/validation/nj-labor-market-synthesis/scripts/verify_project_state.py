#!/usr/bin/env python3
from __future__ import annotations

import csv
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
    "draft source for review",
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


def required_outcomes() -> list[str]:
    brief = read_text(ROOT / "topics" / "brief.md").lower()
    spec = read_text(ROOT / "specs" / "research_question.yaml").lower()
    text = brief + "\n" + spec
    outcomes: list[str] = []
    if "employment" in text:
        outcomes.append("employment")
    if "unemployment" in text:
        outcomes.append("unemployment")
    if "income" in text:
        outcomes.append("income")
    return outcomes


def load_panel_rows() -> tuple[list[str], list[dict[str, str]]]:
    panel = ROOT / "topics" / "data" / "processed" / "longitudinal_panel.csv"
    if not panel.exists():
        return [], []
    with panel.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def check_panel(failures: list[str]) -> None:
    columns, rows = load_panel_rows()
    if not columns or not rows:
        fail("Missing processed longitudinal panel dataset: topics/data/processed/longitudinal_panel.csv", failures)
        return

    lower_cols = [c.lower() for c in columns]

    if "treated" in lower_cols:
        treated_col = columns[lower_cols.index("treated")]
        treated_values = {str(row.get(treated_col, "")).strip() for row in rows if str(row.get(treated_col, "")).strip()}
        if treated_values == {"1"}:
            fail("Panel contains treated=1 for all rows; a real control group is still missing.", failures)

    outcomes = required_outcomes()
    for outcome in outcomes:
        if outcome == "employment":
            present = any("employment" in c or "employed" in c for c in lower_cols)
        elif outcome == "unemployment":
            present = any("unemp" in c for c in lower_cols)
        else:
            present = any("income" in c for c in lower_cols)
        if not present:
            fail(f"Required outcome missing from processed panel: {outcome}", failures)

    source_cols = [c for c in columns if "source" in c.lower() or "provenance" in c.lower()]
    for source_col in source_cols:
        seen = {str(row.get(source_col, "")).strip().lower() for row in rows}
        if any("synthetic" in value for value in seen if value):
            fail(f"Synthetic data detected in panel column {source_col} while integrity.allow_synthetic_data is false.", failures)


def main() -> int:
    failures: list[str] = []
    require_ledgers(failures)
    check_sources(failures)
    check_panel(failures)

    if failures:
        print("VERIFICATION FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print("VERIFICATION PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
