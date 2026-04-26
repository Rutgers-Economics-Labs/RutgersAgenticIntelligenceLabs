"""
Data agent powered by Gemini with function calling.

Capabilities (all available as tools Gemini can invoke):
  - Google Search  — native Gemini grounding, no extra setup
  - browse_page    — Playwright headless browser for JS-rendered pages
  - download_file  — httpx binary download, saves to project repo
  - execute_python — runs pandas/requests/etc. code, returns stdout + result
  - read_file      — reads any file in the project repo
  - write_file     — writes/creates any file in the project repo
  - list_files     — lists a directory in the project repo

Typical uses:
  - Navigate a data portal, find the download URL, and fetch the file
  - Read a source YAML stub and rewrite it with correct endpoint/fields
  - Download a CSV, inspect columns, write a transform YAML
  - Figure out how to configure a YAML source by browsing the docs page
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import sys
import textwrap
import traceback
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import types

from app.core.config import settings

log = logging.getLogger(__name__)

_MODEL = "gemini-3-flash-preview"
_MAX_TURNS = 25
_MAX_FILE_READ = 40_000   # chars
_MAX_BROWSE_CHARS = 20_000

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a data engineering agent working on an economic research project.
You have access to tools that let you:
- Search the web with Google Search (use this freely)
- Browse any URL with a headless Playwright browser (for JS-heavy pages, login flows, download buttons)
- Download data files directly to the project repository
- Execute Python code (pandas, requests, httpx, etc.) for inspection and processing
- Read and write files in the project repo, including YAML configuration files

Your goal is to accomplish the task given to you by actually doing it — not describing how to do it.
If you need to configure a YAML source file, read the existing stub, browse the real data portal to understand
the exact API structure, then write the corrected YAML with real endpoints and field names.
If you need to download a dataset, find the right URL and download it.

YAML source file schema (for .ontology/sources/*.yaml):
  name: <project-slug>-<source-name>
  type: api | csv | html | json | zip
  url: <actual endpoint or download URL>
  response_format: json | csv | xml | zip
  auth:                    # optional
    type: api_key | bearer | basic | none
    header: Authorization  # or X-Api-Key, etc.
    env_var: MY_API_KEY    # name of env var holding the secret
  params:                  # optional query params
    key: value
  description: |
    <what this source provides>
  fields:
    - source: <original field name>
      alias: <clean name>
      description: <optional>

YAML pipeline file schema (for .ontology/pipelines/*.yaml):
  name: <pipeline-name>
  sources:
    - <source-name>
  steps:
    - name: <step-name>
      type: transform | analysis
      plugin: <plugin-name>
      params:
        key: value

Always commit your work at the end by writing a summary of what you did.
When a task is complete, end your final message with: DONE: <one-line summary>
"""

# ── Tool declarations ──────────────────────────────────────────────────────────

_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="browse_page",
        description=(
            "Fetch a web page using a headless Playwright browser. "
            "Use this for JS-rendered pages, data portals, or when requests alone fails. "
            "Returns the visible text content of the page (stripped of HTML)."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "url": types.Schema(type=types.Type.STRING, description="Full URL to browse"),
                "wait_for": types.Schema(
                    type=types.Type.STRING,
                    description="Optional CSS selector to wait for before extracting content",
                ),
            },
            required=["url"],
        ),
    ),
    types.FunctionDeclaration(
        name="download_file",
        description=(
            "Download a file from a URL and save it to the project repository. "
            "Returns the number of bytes written and the saved path."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "url": types.Schema(type=types.Type.STRING, description="Direct download URL"),
                "dest_path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path within the project repo, e.g. 'data/raw/pjm_load.csv'",
                ),
                "headers": types.Schema(
                    type=types.Type.OBJECT,
                    description="Optional HTTP headers, e.g. {\"Ocp-Apim-Subscription-Key\": \"...\"}",
                ),
            },
            required=["url", "dest_path"],
        ),
    ),
    types.FunctionDeclaration(
        name="execute_python",
        description=(
            "Execute a Python code snippet. Has access to pandas, httpx, pathlib, json, csv, "
            "yaml, and the project root directory as PROJECT_ROOT. "
            "Returns stdout + stderr + the string repr of the last expression."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "code": types.Schema(type=types.Type.STRING, description="Python code to run"),
            },
            required=["code"],
        ),
    ),
    types.FunctionDeclaration(
        name="read_file",
        description="Read a file from the project repository. Returns its text content.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path within the project repo",
                ),
            },
            required=["path"],
        ),
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="Write or overwrite a file in the project repository.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path within the project repo",
                ),
                "content": types.Schema(type=types.Type.STRING, description="File content to write"),
            },
            required=["path", "content"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_files",
        description="List files and directories at a path in the project repository.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "path": types.Schema(
                    type=types.Type.STRING,
                    description="Relative path within the project repo (empty string for root)",
                ),
            },
            required=["path"],
        ),
    ),
]

_TOOLS = [
    types.Tool(google_search=types.GoogleSearch()),
    types.Tool(function_declarations=_TOOL_DECLARATIONS),
]


# ── Tool implementations ───────────────────────────────────────────────────────

def _safe_path(project_root: Path, rel: str) -> Path:
    """Resolve a relative path and assert it stays inside the project root."""
    target = (project_root / rel).resolve()
    if not str(target).startswith(str(project_root.resolve())):
        raise ValueError(f"Path escapes project root: {rel}")
    return target


def _browse_page(url: str, wait_for: str | None) -> str:
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=10_000)
                except Exception:
                    pass
            html = page.content()
        finally:
            browser.close()

    text = BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True)
    return text[:_MAX_BROWSE_CHARS]


def _download_file(url: str, dest: Path, headers: dict | None) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        resp = client.get(url, headers=headers or {})
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    return f"Saved {len(resp.content):,} bytes → {dest}"


def _execute_python(code: str, project_root: Path) -> str:
    buf = io.StringIO()
    globs: dict = {
        "PROJECT_ROOT": str(project_root),
        "__builtins__": __builtins__,
    }
    try:
        import pandas, httpx, pathlib, json, csv, yaml  # noqa: F401
        globs.update({"pd": pandas, "httpx": httpx, "Path": pathlib.Path,
                       "json": json, "csv": csv, "yaml": yaml})
    except ImportError:
        pass

    last = None
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            lines = code.strip().split("\n")
            if len(lines) > 1:
                exec("\n".join(lines[:-1]), globs)  # noqa: S102
            try:
                last = eval(lines[-1], globs)  # noqa: S307
            except SyntaxError:
                exec(lines[-1], globs)  # noqa: S102
    except Exception:
        buf.write(traceback.format_exc())

    out = buf.getvalue()
    if last is not None:
        out += f"\n=> {repr(last)[:2000]}"
    return out[:8000] or "(no output)"


async def _execute_tool(
    name: str,
    args: dict[str, Any],
    project_root: Path,
) -> str:
    loop = asyncio.get_event_loop()

    if name == "browse_page":
        return await loop.run_in_executor(
            None, _browse_page, args["url"], args.get("wait_for")
        )

    if name == "download_file":
        dest = _safe_path(project_root, args["dest_path"])
        return await loop.run_in_executor(
            None, _download_file, args["url"], dest, args.get("headers")
        )

    if name == "execute_python":
        return await loop.run_in_executor(
            None, _execute_python, args["code"], project_root
        )

    if name == "read_file":
        p = _safe_path(project_root, args["path"])
        if not p.exists():
            return f"File not found: {args['path']}"
        text = p.read_text(encoding="utf-8", errors="replace")
        return text[:_MAX_FILE_READ]

    if name == "write_file":
        p = _safe_path(project_root, args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(args["content"], encoding="utf-8")
        return f"Written {len(args['content'])} chars → {args['path']}"

    if name == "list_files":
        p = _safe_path(project_root, args.get("path", ""))
        if not p.exists():
            return f"Path not found: {args.get('path', '')}"
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines = [f"{'[dir]' if e.is_dir() else '[file]'} {e.name}" for e in entries[:100]]
        return "\n".join(lines)

    return f"Unknown tool: {name}"


# ── Agentic loop ───────────────────────────────────────────────────────────────

async def run_data_agent(
    project: dict[str, Any],
    task: str,
    *,
    extra_context: str = "",
) -> dict[str, Any]:
    """
    Run one Gemini data agent in an agentic loop with tools.

    Args:
        project:       Convex project record (must have localRepoPath)
        task:          What the agent should accomplish
        extra_context: Extra info to prepend to the prompt

    Returns dict with: task, final_text, files_written, error (if any)
    """
    from app.services import planner_service

    root = planner_service.project_root_from_record(project)
    if root is None:
        return {"task": task, "error": "Project has no localRepoPath"}

    api_key = settings.google_api_key
    if not api_key:
        return {"task": task, "error": "GOOGLE_API_KEY not set"}

    client = genai.Client(api_key=api_key)

    prompt = textwrap.dedent(f"""
        {("Context:\n" + extra_context + "\n") if extra_context else ""}
        Task: {task}

        Project root is at: {root}
        Use read_file / list_files to explore the project structure as needed.
        Use Google Search to find documentation, API specs, or download URLs.
        Use browse_page for JS-heavy portals.
        Use download_file to fetch actual data files into the project.
        Use write_file to write or update YAML configs and data files.
        Use execute_python to inspect data (print dtypes, head, etc.).

        When you are done, say: DONE: <one-line summary of what you accomplished>
    """).strip()

    contents: list = [
        types.Content(role="user", parts=[types.Part.from_text(prompt)])
    ]

    files_written: list[str] = []
    final_text = ""

    for turn in range(_MAX_TURNS):
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                        tools=_TOOLS,
                    ),
                ),
            )
        except Exception as exc:
            log.error("Gemini data agent failed on turn %d: %s", turn, exc)
            return {"task": task, "error": str(exc), "files_written": files_written}

        candidate = response.candidates[0] if response.candidates else None
        if candidate is None:
            break

        contents.append(candidate.content)

        # Collect text and function calls from this turn
        turn_text = ""
        function_calls: list[tuple[str, dict]] = []

        for part in (candidate.content.parts or []):
            if getattr(part, "text", None):
                turn_text += part.text
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                function_calls.append((fc.name, dict(fc.args or {})))

        if turn_text:
            final_text = turn_text
            log.info("Data agent turn %d text: %s…", turn, turn_text[:120])

        if not function_calls:
            break  # Model finished without requesting more tools

        # Execute all tool calls and send results back
        response_parts: list = []
        for tool_name, tool_args in function_calls:
            log.info("Data agent calling tool: %s(%s)", tool_name, list(tool_args.keys()))
            if tool_name == "write_file" and "path" in tool_args:
                files_written.append(tool_args["path"])

            try:
                result = await _execute_tool(tool_name, tool_args, root)
            except Exception as exc:
                result = f"Tool error: {exc}"
                log.warning("Tool %s failed: %s", tool_name, exc)

            response_parts.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": result},
                )
            )

        contents.append(types.Content(role="user", parts=response_parts))

    return {
        "task": task,
        "final_text": final_text,
        "files_written": files_written,
        "turns": turn + 1,
    }


async def run_data_agents(
    project: dict[str, Any],
    agents: list[dict[str, Any]],
    *,
    extra_context: str = "",
) -> list[dict[str, Any]]:
    """
    Run multiple data agents in parallel.

    Each item in `agents` should have:
      - task: str   — what the agent should do

    Returns list of result dicts.
    """
    tasks = [
        run_data_agent(project, a["task"], extra_context=extra_context)
        for a in agents
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"task": agents[i]["task"], "error": str(r)})
        else:
            out.append(r)
    return out
