"""
Base Context Compiler — core logic for building agent prompts.

Task-specific compilers (Analysis, Data Ingestion, etc.) extend this to 
provide specialized framing and constraints.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.runners.base import TaskPayload
from app.runners.contracts import TaskType


class ContextCompiler(ABC):
    @abstractmethod
    def compile(self, payload: TaskPayload) -> str:
        """Produce the final prompt string for the runner."""
        pass

    def _base_context(self, payload: TaskPayload) -> str:
        """Common context shared by all task types."""
        sections = []
        
        # 1. Task Description
        sections.append(f"## Task\n\n{payload.task_description}")
        
        # 2. Acceptance Criteria
        if payload.acceptance_criteria:
            ac_list = "\n".join(f"- {ac}" for ac in payload.acceptance_criteria)
            sections.append(f"## Acceptance Criteria\n\n{ac_list}")
            
        # 3. Work Order Reference
        if payload.work_order_id:
            sections.append(
                f"## RAIL Protocol — Structured I/O (required)\n\n"
                f"You are executing Work Order: {payload.work_order_id}\n"
                f"Full details are available in: {payload.work_order_path}\n"
                f"You MUST read this work order before starting."
            )
            
        # 4. Session Result Requirement
        if payload.session_result_path:
            sections.append(
                f"## Final Output Requirement\n\n"
                f"When you are finished, you MUST write a valid JSON object to:\n"
                f"  {payload.session_result_path}\n\n"
                f"The JSON must conform to the SessionResult schema defined in your Work Order."
            )
            
        return "\n\n".join(sections)


class AnalysisCompiler(ContextCompiler):
    def compile(self, payload: TaskPayload) -> str:
        base = self._base_context(payload)
        framing = (
            "## Persona\n\n"
            "You are a Senior Research Analyst. Your goal is to synthesize data "
            "into clear, evidence-backed findings. You should prioritize "
            "completeness and rigor over speed."
        )
        return f"{framing}\n\n{base}"


class DataIngestionCompiler(ContextCompiler):
    def compile(self, payload: TaskPayload) -> str:
        base = self._base_context(payload)
        framing = (
            "## Persona\n\n"
            "You are a Data Engineering Specialist. Your goal is to discover, "
            "fetch, and structure raw data. You should focus on data quality, "
            "schema alignment, and provenance tracking."
        )
        return f"{framing}\n\n{base}"


class ArtifactWritingCompiler(ContextCompiler):
    def compile(self, payload: TaskPayload) -> str:
        base = self._base_context(payload)
        framing = (
            "## Persona\n\n"
            "You are a Technical Writer and Domain Expert. Your goal is to "
            "produce high-quality reports, memos, or data artifacts based on "
            "prior research findings. Ensure professional tone and citation accuracy."
        )
        return f"{framing}\n\n{base}"


def get_compiler(task_type: TaskType) -> ContextCompiler:
    mapping = {
        TaskType.ANALYSIS: AnalysisCompiler,
        TaskType.DATA_INGESTION: DataIngestionCompiler,
        TaskType.ARTIFACT_WRITING: ArtifactWritingCompiler,
        TaskType.CLAIM_EXTRACTION: AnalysisCompiler, # Fallback to Analysis
        TaskType.SOURCE_DISCOVERY: DataIngestionCompiler,
        TaskType.VERIFICATION: AnalysisCompiler,
        TaskType.HEALTH_REPAIR: AnalysisCompiler,
    }
    compiler_cls = mapping.get(task_type, AnalysisCompiler)
    return compiler_cls()
