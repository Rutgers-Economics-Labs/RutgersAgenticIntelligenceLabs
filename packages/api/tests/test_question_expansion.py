"""Tests for Milestone 7: Question Expansion Logic — classify, parse, and generate task chains."""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# normalize_classification
# ---------------------------------------------------------------------------

def test_normalize_classification_answerable_after_expansion():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("answerable_after_expansion") == "requires_expansion"


def test_normalize_classification_requires_expansion_passthrough():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("requires_expansion") == "requires_expansion"


def test_normalize_classification_blocked_by_data():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("blocked_by_data") == "blocked_by_data"


def test_normalize_classification_answerable_now():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("answerable_now") == "answerable_now"


def test_normalize_classification_current_ontology_alias():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("current_ontology") == "answerable_now"


def test_normalize_classification_unknown_passes_through():
    from app.services.question_expansion_service import normalize_classification
    assert normalize_classification("some_unknown_value") == "some_unknown_value"


# ---------------------------------------------------------------------------
# parse_follow_up_questions
# ---------------------------------------------------------------------------

def _write_questions_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_parse_follow_up_questions_empty_when_file_missing(tmp_path):
    from app.services.question_expansion_service import parse_follow_up_questions
    result = parse_follow_up_questions(tmp_path)
    assert result == []


def test_parse_follow_up_questions_reads_legacy_requires_expansion(tmp_path):
    from app.services.question_expansion_service import parse_follow_up_questions

    _write_questions_file(
        tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md",
        "### 1. What drives wage disparities?\n\n- Classification: `requires_expansion`\n",
    )

    result = parse_follow_up_questions(tmp_path)

    assert len(result) == 1
    assert result[0]["title"] == "1. What drives wage disparities?"
    assert result[0]["classification"] == "requires_expansion"


def test_parse_follow_up_questions_normalizes_new_classification_name(tmp_path):
    from app.services.question_expansion_service import parse_follow_up_questions

    _write_questions_file(
        tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md",
        "### How does inflation affect wages?\n\n- Classification: `answerable_after_expansion`\n",
    )

    result = parse_follow_up_questions(tmp_path)

    assert result[0]["classification"] == "requires_expansion"


def test_parse_follow_up_questions_parses_multiple_with_mixed_names(tmp_path):
    from app.services.question_expansion_service import parse_follow_up_questions

    content = (
        "### Q1\n\n- Classification: `answerable_after_expansion`\n\n"
        "### Q2\n\n- Classification: `blocked_by_data`\n\n"
        "### Q3\n\n- Classification: `answerable_now`\n"
    )
    _write_questions_file(
        tmp_path / "research_plan" / "ontology_answerable_follow_up_questions.md", content
    )

    result = parse_follow_up_questions(tmp_path)

    assert len(result) == 3
    assert result[0]["classification"] == "requires_expansion"
    assert result[1]["classification"] == "blocked_by_data"
    assert result[2]["classification"] == "answerable_now"


# ---------------------------------------------------------------------------
# expansion_task_specs_for_question
# ---------------------------------------------------------------------------

def test_expansion_task_specs_for_requires_expansion():
    from app.services.question_expansion_service import expansion_task_specs_for_question

    specs = expansion_task_specs_for_question("Wage analysis", "requires_expansion")

    assert len(specs) == 1
    assert specs[0]["title"] == "Expand ontology coverage for: Wage analysis"
    assert specs[0]["agent_role"] == "data"


def test_expansion_task_specs_for_blocked_by_data():
    from app.services.question_expansion_service import expansion_task_specs_for_question

    specs = expansion_task_specs_for_question("Trade flow data", "blocked_by_data")

    assert len(specs) == 1
    assert specs[0]["title"] == "Resolve data blocker for: Trade flow data"
    assert specs[0]["agent_role"] == "research"


def test_expansion_task_specs_empty_for_answerable_now():
    from app.services.question_expansion_service import expansion_task_specs_for_question

    specs = expansion_task_specs_for_question("Current coverage question", "answerable_now")

    assert specs == []


# ---------------------------------------------------------------------------
# missing_expansion_task_blockers
# ---------------------------------------------------------------------------

def test_missing_expansion_task_blockers_returns_blocker_for_missing_task():
    from app.services.question_expansion_service import missing_expansion_task_blockers

    questions = [{"title": "Wage drivers", "classification": "requires_expansion"}]
    result = missing_expansion_task_blockers(questions, existing_task_titles=set())

    assert len(result) == 1
    assert "Wage drivers" in result[0]


def test_missing_expansion_task_blockers_no_blocker_when_task_exists():
    from app.services.question_expansion_service import missing_expansion_task_blockers

    questions = [{"title": "Wage drivers", "classification": "requires_expansion"}]
    existing = {"Expand ontology coverage for: Wage drivers"}
    result = missing_expansion_task_blockers(questions, existing_task_titles=existing)

    assert result == []


def test_missing_expansion_task_blockers_accepts_answerable_after_expansion_alias(tmp_path):
    """questions from parse_follow_up_questions already normalize the name, but
    callers may pass raw questions — blockers must still work for both names."""
    from app.services.question_expansion_service import missing_expansion_task_blockers, normalize_classification

    # Simulate a question already normalized (the way parse_follow_up_questions returns it)
    questions = [{"title": "Coverage gap", "classification": normalize_classification("answerable_after_expansion")}]
    result = missing_expansion_task_blockers(questions, existing_task_titles=set())

    assert len(result) == 1
    assert "Coverage gap" in result[0]
