"""
Provider-agnostic LLM service backed by LiteLLM.

Supports any model string LiteLLM understands:
  - "claude-sonnet-4-6"                           → Anthropic (ANTHROPIC_API_KEY)
  - "gemini/gemini-flash-latest"                  → Google (GOOGLE_API_KEY)
  - "openrouter/anthropic/claude-3.5-sonnet"      → OpenRouter (OPENROUTER_API_KEY)
  - "gpt-4o"                                      → OpenAI (OPENAI_API_KEY)

Switch models at runtime by passing `model=` or changing AI_MODEL in .env.
"""
import json
import os
from typing import Any, AsyncGenerator

import litellm
from litellm import acompletion

from app.core.config import settings

# Silence LiteLLM's verbose success logs
litellm.success_callback = []
litellm.set_verbose = False


def ensure_env_keys() -> None:
    """Push API keys from settings into os.environ so LiteLLM can read them."""
    if settings.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
    if settings.openai_api_key:
        os.environ.setdefault("OPENAI_API_KEY", settings.openai_api_key)
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    if settings.openrouter_api_key:
        os.environ.setdefault("OPENROUTER_API_KEY", settings.openrouter_api_key)


async def complete(
    messages: list[dict],
    model: str | None = None,
    tools: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Any:
    """Non-streaming completion. Returns the full LiteLLM response object."""
    ensure_env_keys()
    kwargs: dict[str, Any] = {
        "model": model or settings.ai_model,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.ai_temperature,
        "max_tokens": max_tokens or settings.ai_max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return await acompletion(**kwargs)


async def stream_text(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming text completion. Yields text delta strings."""
    ensure_env_keys()
    response = await acompletion(
        model=model or settings.ai_model,
        messages=messages,
        temperature=temperature if temperature is not None else settings.ai_temperature,
        max_tokens=max_tokens or settings.ai_max_tokens,
        stream=True,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def stream_agent(
    messages: list[dict],
    tools: list[dict],
    model: str | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Streaming agent loop with tool use.

    Yields dicts with `type` field:
      {"type": "text_delta",   "content": str}
      {"type": "tool_call",    "id": str, "name": str, "args": dict}
      {"type": "tool_result",  "id": str, "name": str, "result": any}
      {"type": "done"}

    The caller must supply a `tool_executor` by monkey-patching or wrapping;
    use the higher-level `agent_service.run_chat` instead.
    """
    ensure_env_keys()
    m = model or settings.ai_model

    # This function only handles ONE streaming turn.
    # The full loop (with tool execution) lives in agent_service.
    response = await acompletion(
        model=m,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        stream=True,
    )

    tool_calls_buf: dict[int, dict] = {}
    text_buf = ""

    async for chunk in response:
        delta = chunk.choices[0].delta

        if delta.content:
            text_buf += delta.content
            yield {"type": "text_delta", "content": delta.content}

        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buf:
                    tool_calls_buf[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.id:
                    tool_calls_buf[idx]["id"] = tc.id
                if tc.function and tc.function.name:
                    tool_calls_buf[idx]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    tool_calls_buf[idx]["arguments"] += tc.function.arguments

    # Yield accumulated tool calls at end of stream
    for idx in sorted(tool_calls_buf.keys()):
        tc = tool_calls_buf[idx]
        try:
            args = json.loads(tc["arguments"]) if tc["arguments"] else {}
        except json.JSONDecodeError:
            args = {"_raw": tc["arguments"]}
        yield {"type": "tool_call", "id": tc["id"], "name": tc["name"], "args": args}

    # Signal end of this streaming turn, include whether tool calls were made
    yield {"type": "_turn_end", "has_tool_calls": bool(tool_calls_buf), "text": text_buf,
           "raw_tool_calls": list(tool_calls_buf.values())}
