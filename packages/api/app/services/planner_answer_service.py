"""
Planner Answer Service — 3-tier Q&A resolver for agents mid-session.

Tier 1: Semantic Cache (Similarity search over historical qa_log.json)
Tier 2: Planner LLM (Context-aware resolution based on project docs/plan)
Tier 3: Human Escalation (Operator inbox for unresolved questions)
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.services import embedding_service, llm_service, planner_service
from app.core.config import settings

logger = logging.getLogger(__name__)

QA_LOG_REL_PATH = Path("research_plan") / "decisions" / "qa_log.json"


async def resolve_question(
    project_slug: str,
    session_id: str,
    question: str,
    *,
    threshold: float = 0.85,
) -> dict[str, Any]:
    """
    The main entry point for resolving an agent's question.
    Returns a dict with 'answer', 'tier', and 'status'.
    """
    import hashlib
    question_id = hashlib.sha256(f"{session_id}:{question}".encode("utf-8")).hexdigest()

    project = await planner_service.resolve_project_reference(project_slug)
    root = planner_service.project_root_from_record(project)
    if not root:
        raise ValueError(f"Project {project_slug} has no local repo path")

    qa_log_path = root / QA_LOG_REL_PATH
    qa_log_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Tier 1: Cache Lookup
    cached_answer = await _check_cache(qa_log_path, question, threshold=threshold)
    if cached_answer:
        logger.info("Q&A: Tier 1 cache hit for question: %s", question[:50])
        return {
            "question_id": question_id,
            "answer": cached_answer["answer"],
            "tier": 1,
            "status": "resolved",
            "metadata": {"original_question": cached_answer["question"]},
        }

    # 2. Tier 2: Planner LLM
    logger.info("Q&A: Tier 1 miss, attempting Tier 2 (LLM) for: %s", question[:50])
    llm_response = await _ask_planner_llm(project, question)
    
    if llm_response["confidence"] >= 0.7:
        answer = llm_response["answer"]
        _log_qa(qa_log_path, session_id, question, answer, tier=2, question_id=question_id)
        return {
            "question_id": question_id,
            "answer": answer,
            "tier": 2,
            "status": "resolved",
        }

    # 3. Tier 3: Human Escalation
    logger.info("Q&A: Tier 2 uncertain, escalating to Tier 3 (Human)")
    _log_qa(qa_log_path, session_id, question, None, tier=3, status="pending", question_id=question_id)
    return {
        "question_id": question_id,
        "answer": "I am unsure and have escalated this to the project operator. Please wait or proceed with other tasks if possible.",
        "tier": 3,
        "status": "pending",
    }


async def _check_cache(qa_log_path: Path, question: str, threshold: float) -> dict | None:
    if not qa_log_path.exists():
        return None

    try:
        log = json.loads(qa_log_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Filter for resolved questions with answers
    candidates = [entry for entry in log if entry.get("status") == "resolved" and entry.get("answer")]
    if not candidates:
        return None

    # Simple exact match first
    for entry in candidates:
        if entry["question"].strip().lower() == question.strip().lower():
            return entry

    # Semantic similarity (if embedding service is available)
    try:
        # We'll use a simplified version of embedding search here
        # In a more robust impl, we'd index the qa_log.json
        model_name, [q_vec] = await embedding_service._embed_texts([question])
        
        best_match = None
        best_score = -1.0
        
        # We only embed candidates on the fly for small logs. 
        # For large logs, we'd use a real vector index.
        candidate_texts = [c["question"] for c in candidates]
        _, c_vecs = await embedding_service._embed_texts(candidate_texts, model_name=model_name)
        
        for entry, c_vec in zip(candidates, c_vecs):
            score = embedding_service._cosine_similarity(q_vec, c_vec)
            if score > best_score:
                best_score = score
                best_match = entry
        
        if best_score >= threshold:
            return best_match
    except Exception as e:
        logger.warning("Q&A: Cache similarity search failed: %s", e)
    
    return None


async def _ask_planner_llm(project: dict, question: str) -> dict[str, Any]:
    """
    Ask the LLM to answer the question based on project context.
    Returns {"answer": str, "confidence": float}
    """
    # Gather context
    root = planner_service.project_root_from_record(project)
    context_bits = []
    
    # Add project description
    context_bits.append(f"Project Description: {project.get('description', 'N/A')}")
    
    # Add current plan if available
    plan_path = root / "research_plan" / "current_plan.md"
    if plan_path.exists():
        context_bits.append(f"Current Plan:\n{plan_path.read_text(encoding='utf-8')}")
    
    # Add methodology or guidelines if they exist
    for doc_name in ["methodology.md", "README.md", "GEMINI.md"]:
        doc_path = root / doc_name
        if doc_path.exists():
            context_bits.append(f"{doc_name}:\n{doc_path.read_text(encoding='utf-8')[:2000]}") # truncate large docs

    context = "\n\n".join(context_bits)
    
    prompt = f"""You are the Project Planner for RAIL (Rutgers Agentic Intelligence Labs).
An autonomous research agent is asking a question mid-session.
You must answer based ONLY on the project context provided below.

If the answer is clearly in the context, provide it and set confidence to 1.0.
If you can reasonably infer the answer, provide it and set confidence between 0.7 and 0.9.
If you are unsure or the context is insufficient, state that you don't know and set confidence to 0.0.

Format your response as a JSON object:
{{
  "answer": "Your detailed answer here",
  "confidence": 0.0 to 1.0,
  "rationale": "Why you gave this answer"
}}

Project Context:
{context}

Agent Question:
{question}
"""

    try:
        response = await llm_service.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, # deterministic for planning
        )
        content = response.choices[0].message.content
        # Basic JSON extraction
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            return json.loads(match.group())
        # Fallback if LLM didn't return pure JSON
        return {"answer": content, "confidence": 0.5, "rationale": "Raw LLM output"}
    except Exception as e:
        logger.error("Q&A: Tier 2 LLM failed: %s", e)
        return {"answer": "Error calling LLM", "confidence": 0.0}


def _log_qa(
    qa_log_path: Path,
    session_id: str,
    question: str,
    answer: str | None,
    tier: int,
    status: str = "resolved",
    question_id: str | None = None,
):
    if not question_id:
        import hashlib
        question_id = hashlib.sha256(f"{session_id}:{question}".encode("utf-8")).hexdigest()

    entry = {
        "question_id": question_id,
        "session_id": session_id,
        "question": question,
        "answer": answer,
        "tier": tier,
        "status": status,
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat() + "Z",
    }
    
    log = []
    if qa_log_path.exists():
        try:
            log = json.loads(qa_log_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    
    # Overwrite if exists
    updated = False
    for i, item in enumerate(log):
        if item.get("question_id") == question_id:
            log[i] = entry
            updated = True
            break
            
    if not updated:
        log.append(entry)
        
    qa_log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
