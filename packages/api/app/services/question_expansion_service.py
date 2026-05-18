"""Question expansion logic: parse, classify, and generate task chains for follow-up questions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

FOLLOW_UP_QUESTIONS_PATH = "research_plan/ontology_answerable_follow_up_questions.md"

# Canonical classification names used throughout the codebase.
CANONICAL_CLASSIFICATIONS = {
    "answerable_now",
    "answerable_after_requery",
    "requires_expansion",
    "blocked_by_data",
}

# Accept both naming conventions by normalizing aliases to canonical names.
_CLASSIFICATION_ALIASES: dict[str, str] = {
    "answerable_after_expansion": "requires_expansion",
    "requires_expansion": "requires_expansion",
    "blocked_by_data": "blocked_by_data",
    "answerable_now": "answerable_now",
    "answerable_after_requery": "answerable_after_requery",
    "current_ontology": "answerable_now",
}


def normalize_classification(raw: str) -> str:
    """Normalize a raw classification string to a canonical name.

    Accepts both the planner-prompt style ('answerable_after_expansion')
    and the legacy operational style ('requires_expansion').
    """
    normalized = str(raw or "").strip().lower()
    return _CLASSIFICATION_ALIASES.get(normalized, normalized)


def parse_follow_up_questions(project_root: Path | str) -> list[dict[str, Any]]:
    """Parse ontology_answerable_follow_up_questions.md and return classified questions.

    Each item has: title (str), classification (str | None).
    Classification names are normalized via normalize_classification().
    """
    path = Path(project_root) / FOLLOW_UP_QUESTIONS_PATH
    if not path.exists():
        return []

    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            if current:
                questions.append(current)
            current = {"title": line[4:].strip(), "classification": None}
            continue
        if current is None:
            continue
        if line.startswith("- Classification:"):
            parts = line.split("`")
            raw_class = parts[1].strip() if len(parts) >= 2 else line.removeprefix("- Classification:").strip()
            current["classification"] = normalize_classification(raw_class)
    if current:
        questions.append(current)
    return questions


def expansion_task_specs_for_question(question_title: str, classification: str) -> list[dict[str, Any]]:
    """Return a list of task-spec dicts to create for a classified follow-up question.

    For requires_expansion: returns an ontology expansion task.
    For blocked_by_data: returns a data-blocker investigation task.
    For other classifications: returns an empty list (no task chain needed).
    """
    if classification == "requires_expansion":
        return [
            {
                "title": f"Expand ontology coverage for: {question_title}",
                "description": (
                    f"Create the ontology expansion needed to answer: {question_title}. "
                    "Translate into concrete source, pipeline, transform, or ontology-verification work."
                ),
                "status": "ready",
                "agent_role": "data",
                "repo_paths": [
                    ".ontology/sources",
                    ".ontology/pipelines",
                    ".ontology/transforms",
                    "research_plan",
                    "topics",
                ],
                "acceptance_criteria": [
                    "the missing ontology coverage is translated into concrete source or pipeline work",
                    "the task records which source, transform, or relationship expansion is required",
                    "follow-on ontology verification work is identified if hydration changes are needed",
                ],
                "runner": "codex_cli",
            }
        ]
    if classification == "blocked_by_data":
        return [
            {
                "title": f"Resolve data blocker for: {question_title}",
                "description": (
                    f"Investigate and document the missing data access needed to answer: {question_title}. "
                    "Record the missing source, access blocker, and what would unblock ontology expansion."
                ),
                "status": "ready",
                "agent_role": "research",
                "repo_paths": ["research_plan", "topics", ".ontology/sources"],
                "acceptance_criteria": [
                    "the missing source or access blocker is documented explicitly",
                    "the task records whether the blocker is licensing, permissions, provenance, or coverage",
                    "the repo contains the next recommended expansion path if the blocker can be resolved",
                ],
                "runner": "codex_cli",
            }
        ]
    return []


def missing_expansion_task_blockers(
    questions: list[dict[str, Any]],
    existing_task_titles: set[str],
) -> list[str]:
    """Return blocker strings for questions that need expansion tasks but don't have them yet."""
    blockers: list[str] = []
    for question in questions:
        title = str(question.get("title") or "").strip()
        classification = str(question.get("classification") or "").strip()
        if not title:
            continue
        for spec in expansion_task_specs_for_question(title, classification):
            if spec["title"] not in existing_task_titles:
                if classification == "requires_expansion":
                    blockers.append(f"Missing ontology expansion task for follow-up question: {title}")
                elif classification == "blocked_by_data":
                    blockers.append(f"Missing data-blocker task for follow-up question: {title}")
    return blockers
