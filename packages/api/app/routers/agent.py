"""
Agent endpoints for RAIL.

POST /agent/chat       — streaming SSE agent conversation
POST /agent/infer-schema — CSV/JSON sample → suggested YAML configs
"""
import json
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services import agent_service, llm_service, planner_runtime, planner_service

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Chat (SSE streaming)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{role, content}, ...]
    model: str | None = None
    session_id: str | None = None


@router.post("/chat")
async def agent_chat(req: ChatRequest, project: str | None = Query(default=None)):
    """
    Stream an agent response as Server-Sent Events.

    Each SSE event has a `data` field with a JSON object:
      {"type": "text_delta",   "content": str}
      {"type": "tool_call",    "id": str, "name": str, "args": dict}
      {"type": "tool_result",  "id": str, "name": str, "result": any}
      {"type": "done",         "new_messages": list}
      {"type": "error",        "message": str}
    """
    async def event_stream():
        try:
            if project:
                project_record = await planner_service.get_project_by_slug(project)
                assistant_message = ""
                async for event in planner_runtime.stream_planner_turn(
                    project=project_record,
                    user_message=req.message,
                    history=req.history,
                    model=req.model,
                    persist=True,
                ):
                    if event["type"] == "done":
                        assistant_message = event.get("assistant_message", "")
                        yield f"data: {json.dumps({'type': 'done', 'new_messages': [{'role': 'assistant', 'content': assistant_message}]}, default=str)}\n\n"
                    else:
                        yield f"data: {json.dumps(event, default=str)}\n\n"
                return
            async for event in agent_service.run_chat(
                user_message=req.message,
                history=req.history,
                model=req.model,
                project_slug=project,
            ):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Schema inference
# ---------------------------------------------------------------------------

class InferSchemaRequest(BaseModel):
    """Either provide `sample` (JSON string / CSV header row) or `description`."""
    sample: str | None = None
    description: str | None = None
    domain: str = "economics"
    model: str | None = None


@router.post("/infer-schema")
async def infer_schema(req: InferSchemaRequest):
    """
    Given a data sample or description, suggest YAML configs:
    - An API/CSV config
    - An ontology schema
    Returns {api_yaml, ontology_yaml, explanation}.
    """
    if not req.sample and not req.description:
        raise HTTPException(status_code=400, detail="Provide either `sample` or `description`")

    context = ""
    if req.sample:
        context += f"Data sample:\n```\n{req.sample[:3000]}\n```\n\n"
    if req.description:
        context += f"Description: {req.description}\n\n"

    system = (
        "You are an expert in knowledge graphs and YAML config design for RAIL. "
        "Given a data sample or description, output two YAML configs:\n"
        "1. An API/CSV source config (type: csv or api)\n"
        "2. An ontology schema config\n\n"
        "Output ONLY valid YAML blocks in this exact format (no extra text):\n"
        "```yaml api_config\n<api yaml>\n```\n\n"
        "```yaml ontology_config\n<ontology yaml>\n```\n\n"
        "```text explanation\n<one paragraph explanation>\n```"
    )

    response = await llm_service.complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ],
        model=req.model,
        temperature=0.2,
    )
    raw = response.choices[0].message.content

    # Parse out the three blocks
    def extract_block(tag: str) -> str:
        start = raw.find(f"```{tag}")
        if start == -1:
            return ""
        start = raw.find("\n", start) + 1
        end = raw.find("```", start)
        return raw[start:end].strip() if end != -1 else raw[start:].strip()

    return {
        "api_yaml": extract_block("yaml api_config"),
        "ontology_yaml": extract_block("yaml ontology_config"),
        "explanation": extract_block("text explanation"),
        "raw": raw,
    }


# ---------------------------------------------------------------------------
# Available models list (for frontend selector)
# ---------------------------------------------------------------------------

AVAILABLE_MODELS = [
    # Anthropic
    {"id": "claude-sonnet-4-6",                          "label": "Claude Sonnet 4.6 (Anthropic)"},
    {"id": "claude-opus-4-6",                            "label": "Claude Opus 4.6 (Anthropic)"},
    {"id": "claude-haiku-4-5-20251001",                  "label": "Claude Haiku 4.5 (Anthropic)"},
    # Google — Gemini 3 series
    {"id": "gemini/gemini-3.1-pro-preview",              "label": "Gemini 3.1 Pro Preview (Google)"},
    {"id": "gemini/gemini-3-flash-preview",              "label": "Gemini 3 Flash Preview (Google)"},
    {"id": "gemini/gemini-3.1-flash-lite-preview",       "label": "Gemini 3.1 Flash Lite Preview (Google)"},
    # OpenAI
    {"id": "gpt-4o",                                     "label": "GPT-4o (OpenAI)"},
    {"id": "gpt-4o-mini",                                "label": "GPT-4o Mini (OpenAI)"},
    # OpenRouter
    {"id": "openrouter/anthropic/claude-3.5-sonnet",     "label": "Claude 3.5 Sonnet (OpenRouter)"},
    {"id": "openrouter/google/gemini-flash-1.5",         "label": "Gemini Flash (OpenRouter)"},
    {"id": "openrouter/meta-llama/llama-3.1-70b-instruct", "label": "Llama 3.1 70B (OpenRouter)"},
]


@router.get("/models")
async def list_models():
    """Return the list of supported model IDs for the frontend selector."""
    from app.core.config import settings
    return {"models": AVAILABLE_MODELS, "default": settings.ai_model}
