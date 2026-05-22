"""Phase 4 — Q&A Protocol tests.

Covers:
  1. Tier 1: Cache hits (exact and semantic).
  2. Tier 2: LLM-based resolution.
  3. Tier 3: Human escalation for uncertain questions.
  4. qa_log.json persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.planner_answer_service import resolve_question, _check_cache

@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    tasks_dir = tmp_path / "research_plan" / "tasks"
    tasks_dir.mkdir(parents=True)
    decisions_dir = tmp_path / "research_plan" / "decisions"
    decisions_dir.mkdir(parents=True)
    return tmp_path

@pytest.fixture
def mock_planner_service(project_root):
    with patch("app.services.planner_answer_service.planner_service") as mock:
        mock.get_project_by_slug = AsyncMock(return_value={"slug": "test-proj", "localRepoPath": str(project_root)})
        mock.project_root_from_record.return_value = project_root
        yield mock

class TestQACache:
    @pytest.mark.asyncio
    async def test_exact_match_cache_hit(self, project_root):
        qa_log_path = project_root / "research_plan" / "decisions" / "qa_log.json"
        log = [
            {
                "question": "What is the capital of France?",
                "answer": "Paris",
                "status": "resolved"
            }
        ]
        qa_log_path.write_text(json.dumps(log))
        
        result = await _check_cache(qa_log_path, "What is the capital of France?", threshold=0.9)
        assert result is not None
        assert result["answer"] == "Paris"

    @pytest.mark.asyncio
    @patch("app.services.planner_answer_service.embedding_service")
    async def test_semantic_match_cache_hit(self, mock_embedding, project_root):
        mock_embedding._embed_texts = AsyncMock()
        mock_embedding._embed_texts.side_effect = [
            ("model", [[0.1, 0.2]]), # question vector
            ("model", [[0.11, 0.21]]) # candidate vector
        ]
        mock_embedding._cosine_similarity.return_value = 0.99
        
        qa_log_path = project_root / "research_plan" / "decisions" / "qa_log.json"
        log = [
            {
                "question": "What is France's capital?",
                "answer": "Paris",
                "status": "resolved"
            }
        ]
        qa_log_path.write_text(json.dumps(log))
        
        result = await _check_cache(qa_log_path, "What is the capital of France?", threshold=0.9)
        assert result is not None
        assert result["answer"] == "Paris"

class TestQAResolution:
    @pytest.mark.asyncio
    @patch("app.services.planner_answer_service._check_cache")
    @patch("app.services.planner_answer_service._ask_planner_llm")
    async def test_tier2_resolution(self, mock_llm, mock_cache, mock_planner_service, project_root):
        mock_cache.return_value = None
        mock_llm.return_value = {"answer": "Use SA series.", "confidence": 0.9}
        
        result = await resolve_question("test-proj", "sess-1", "Which series should I use?")
        
        assert result["tier"] == 2
        assert result["answer"] == "Use SA series."
        assert result["status"] == "resolved"
        
        # Verify log entry
        qa_log_path = project_root / "research_plan" / "decisions" / "qa_log.json"
        log = json.loads(qa_log_path.read_text())
        assert len(log) == 1
        assert log[0]["tier"] == 2
        assert log[0]["answer"] == "Use SA series."

    @pytest.mark.asyncio
    @patch("app.services.planner_answer_service._check_cache")
    @patch("app.services.planner_answer_service._ask_planner_llm")
    async def test_tier3_escalation(self, mock_llm, mock_cache, mock_planner_service, project_root):
        mock_cache.return_value = None
        mock_llm.return_value = {"answer": "I don't know.", "confidence": 0.2}
        
        result = await resolve_question("test-proj", "sess-1", "Unknown question?")
        
        assert result["tier"] == 3
        assert result["status"] == "pending"
        
        # Verify log entry
        qa_log_path = project_root / "research_plan" / "decisions" / "qa_log.json"
        log = json.loads(qa_log_path.read_text())
        assert log[0]["tier"] == 3
        assert log[0]["status"] == "pending"
        assert log[0]["answer"] is None
