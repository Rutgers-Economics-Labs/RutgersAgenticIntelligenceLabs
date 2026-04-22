from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path
from typing import Any

import yaml

from app.services import llm_service, registry_service


READY = "ready"
DRAFT = "draft_for_review"
MISSING = "missing_auth_or_manual"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "research-project"


def brief_hash(brief: str) -> str:
    return hashlib.sha256(brief.encode("utf-8")).hexdigest()


def default_repo_target(base_dir: Path, slug: str) -> Path:
    return base_dir / "generated_projects" / slug


async def build_preview(brief: str, *, model: str | None = None) -> dict[str, Any]:
    graph = await parse_brief_to_graph(brief, model=model)
    project = infer_project_metadata(graph)
    sources = await recommend_sources(graph, project_slug=project["slug"])
    ontology = draft_ontology(project, graph, sources)
    pipeline = draft_pipeline(project, graph, sources)
    repo_files = render_repo_files(project, graph, sources, ontology, pipeline)
    return {
        "briefHash": brief_hash(brief),
        "project": project,
        "researchGraph": graph,
        "sourceCandidates": sources,
        "ontology": ontology,
        "pipeline": pipeline,
        "repoFiles": repo_files,
        "readiness": summarize_readiness(sources),
        "hydrationReady": all(source["readiness"] == READY for source in sources) and bool(sources),
        "nextAction": "Review proposed assets, then create the project. Hydration is a separate approval step.",
    }


async def parse_brief_to_graph(brief: str, *, model: str | None = None) -> dict[str, Any]:
    heuristic = _heuristic_graph(brief)
    prompt = textwrap.dedent(
        """
        You convert research briefs into a normalized JSON research graph for RAIL.
        Return JSON only with this schema:
        {
          "title": str,
          "summary": str,
          "audience": str,
          "objective": str,
          "causal_questions": [str],
          "outcomes": [str],
          "units_of_analysis": [str],
          "geographies": [str],
          "time_windows": [str],
          "methods": [str],
          "deliverables": [str],
          "controls": [str],
          "entities": [str],
          "measures": [str],
          "source_hints": [str]
        }
        Keep items concise and domain-agnostic. If uncertain, prefer empty arrays rather than invention.
        """
    ).strip()

    try:
        response = await llm_service.complete(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": brief[:12000]},
            ],
            model=model,
            temperature=0.1,
            max_tokens=3000,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = _extract_json(raw)
        return _normalize_graph({**heuristic, **parsed})
    except Exception:
        return _normalize_graph(heuristic)


def infer_project_metadata(graph: dict[str, Any]) -> dict[str, Any]:
    title = graph.get("title") or "Research Project"
    slug = slugify(title)
    summary = graph.get("summary") or graph.get("objective") or "Repo-backed research kickoff generated from a brief."
    return {
        "name": title,
        "slug": slug,
        "description": summary[:280],
        "approach": "ontology-first",
    }


async def recommend_sources(graph: dict[str, Any], *, project_slug: str) -> list[dict[str, Any]]:
    queries = [*graph.get("source_hints", []), *graph.get("outcomes", []), *graph.get("controls", [])]
    candidates: dict[str, dict[str, Any]] = {}
    for query in [q for q in queries if q][:8]:
        for entry in await registry_service.search_registry_entries(query_text=query, limit=4):
            key = f"{entry['provider']}:{entry['id']}"
            if key in candidates:
                continue
            slug = slugify(f"{project_slug}-{entry['provider']}-{entry['id']}")
            candidates[key] = {
                "slug": slug,
                "name": entry["name"],
                "provider": entry["provider"],
                "externalId": entry["id"],
                "description": entry["description"],
                "readiness": READY,
                "reason": f"Matched registry source for '{query}'.",
                "configKind": "api",
                "content": entry["exampleYaml"],
            }

    # Convert generic or unsupported hints into reviewable draft notes/configs.
    existing_names = {item["name"].lower() for item in candidates.values()}
    for hint in graph.get("source_hints", [])[:8]:
        lower = hint.lower()
        if any(lower in name for name in existing_names):
            continue
        if any(token in lower for token in ("census", "acs", "fred", "bls", "world bank", "worldbank")):
            readiness = DRAFT
        else:
            readiness = MISSING
        slug = slugify(f"{project_slug}-{hint}")
        candidates[f"hint:{slug}"] = {
            "slug": slug,
            "name": hint,
            "provider": "manual",
            "externalId": None,
            "description": f"Derived from the brief: {hint}",
            "readiness": readiness,
            "reason": "No exact runnable registry match was found; review is required.",
            "configKind": "api",
            "content": _draft_source_yaml(slug, hint, readiness),
        }

    return list(candidates.values())[:12]


def draft_ontology(project: dict[str, Any], graph: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    class_names = _dedupe_title_case(
        [
            "ResearchProject",
            "ResearchQuestion",
            "DataSource",
            "Geography",
            "Measure",
            "Observation",
            *graph.get("units_of_analysis", []),
            *graph.get("entities", []),
        ]
    )
    ontology = {
        "uri": f"http://rail.rutgers.edu/ontology/{project['slug']}",
        "classes": [{"name": cls} for cls in class_names],
        "data_properties": [
            {"name": "hasName", "domain": "ResearchProject", "range": "str"},
            {"name": "hasDescription", "domain": "ResearchQuestion", "range": "str"},
            {"name": "hasUnit", "domain": "Measure", "range": "str"},
            {"name": "hasValue", "domain": "Observation", "range": "float"},
            {"name": "hasDate", "domain": "Observation", "range": "str"},
        ],
        "object_properties": [
            {"name": "usesSource", "domain": "ResearchProject", "range": "DataSource"},
            {"name": "aboutMeasure", "domain": "Observation", "range": "Measure"},
            {"name": "observedFor", "domain": "Observation", "range": "Geography"},
        ],
    }
    content = yaml.safe_dump(ontology, sort_keys=False, allow_unicode=False)
    return {
        "name": f"{project['name']} Ontology",
        "slug": f"{project['slug']}-ontology",
        "content": content,
        "parsedSpec": ontology,
        "isPublic": False,
        "summary": f"{len(class_names)} proposed classes based on the brief.",
    }


def draft_pipeline(project: dict[str, Any], graph: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    step_sources = [source for source in sources if source["readiness"] in {READY, DRAFT}]
    steps = []
    for source in step_sources:
        steps.append(
            {
                "name": f"load_{slugify(source['slug'])}",
                "api": source["slug"],
                "class": "Observation",
                "uri": f"http://rail.rutgers.edu/ontology/{project['slug']}#Observation_{{id}}",
            }
        )
    pipeline = {
        "name": f"{project['slug']}-pipeline",
        "ontology": f"{project['slug']}-ontology",
        "steps": steps,
    }
    content = yaml.safe_dump(pipeline, sort_keys=False, allow_unicode=False)
    return {
        "name": f"{project['name']} Pipeline",
        "slug": f"{project['slug']}-pipeline",
        "content": content,
        "parsedSpec": pipeline,
        "referencedApiSlugs": [source["slug"] for source in step_sources],
        "isPublic": False,
        "summary": f"{len(steps)} draft ingestion steps.",
    }


def render_repo_files(
    project: dict[str, Any],
    graph: dict[str, Any],
    sources: list[dict[str, Any]],
    ontology: dict[str, Any],
    pipeline: dict[str, Any],
) -> list[dict[str, str]]:
    question = {
        "title": graph.get("title"),
        "objective": graph.get("objective"),
        "audience": graph.get("audience"),
        "causal_questions": graph.get("causal_questions", []),
        "outcomes": graph.get("outcomes", []),
        "units_of_analysis": graph.get("units_of_analysis", []),
        "geographies": graph.get("geographies", []),
        "time_windows": graph.get("time_windows", []),
        "methods": graph.get("methods", []),
        "deliverables": graph.get("deliverables", []),
        "controls": graph.get("controls", []),
    }
    summary = summarize_readiness(sources)
    files = [
        {"path": "specs/research_question.yaml", "content": yaml.safe_dump(question, sort_keys=False, allow_unicode=False)},
        {"path": "research_plan/current_plan.md", "content": _current_plan_md(project, graph, sources)},
        {"path": "research_plan/task_board.md", "content": _task_board_md(sources)},
        {"path": "research_plan/graph/summary.yaml", "content": yaml.safe_dump(graph, sort_keys=False, allow_unicode=False)},
        {"path": "research_plan/graph/sources.yaml", "content": yaml.safe_dump({"sources": sources, "summary": summary}, sort_keys=False, allow_unicode=False)},
        {"path": "topics/brief.md", "content": _brief_topic_md(graph)},
        {"path": "topics/source_notes.md", "content": _source_notes_md(sources)},
        {"path": f".ontology/ontologies/{ontology['slug']}.yaml", "content": ontology["content"]},
        {"path": f".ontology/pipelines/{pipeline['slug']}.yaml", "content": pipeline["content"]},
    ]
    for source in sources:
        if source.get("content"):
            files.append({"path": f".ontology/sources/{source['slug']}.yaml", "content": source["content"]})
    return files


def write_repo_files(root: Path, repo_files: list[dict[str, str]]) -> None:
    for file in repo_files:
        path = (root / file["path"]).resolve()
        if not str(path).startswith(str(root.resolve())):
            raise ValueError(f"Path traversal not allowed: {file['path']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(file["content"], encoding="utf-8")


def summarize_readiness(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {READY: 0, DRAFT: 0, MISSING: 0}
    for source in sources:
        counts[source["readiness"]] = counts.get(source["readiness"], 0) + 1
    return counts


def _extract_json(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return {}
    return json.loads(raw[start : end + 1])


def _normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "title": graph.get("title") or "Research Project",
        "summary": graph.get("summary") or "",
        "audience": graph.get("audience") or "",
        "objective": graph.get("objective") or "",
        "causal_questions": _as_list(graph.get("causal_questions")),
        "outcomes": _as_list(graph.get("outcomes")),
        "units_of_analysis": _as_list(graph.get("units_of_analysis")),
        "geographies": _as_list(graph.get("geographies")),
        "time_windows": _as_list(graph.get("time_windows")),
        "methods": _as_list(graph.get("methods")),
        "deliverables": _as_list(graph.get("deliverables")),
        "controls": _as_list(graph.get("controls")),
        "entities": _as_list(graph.get("entities")),
        "measures": _as_list(graph.get("measures")),
        "source_hints": _as_list(graph.get("source_hints")),
    }
    normalized["entities"] = _dedupe_title_case(normalized["entities"] + normalized["units_of_analysis"])
    normalized["measures"] = _dedupe(normalized["measures"] + normalized["outcomes"])
    if not normalized["summary"]:
        normalized["summary"] = normalized["objective"] or "Research kickoff generated from a brief."
    return normalized


def _heuristic_graph(brief: str) -> dict[str, Any]:
    lines = [line.strip() for line in brief.splitlines() if line.strip()]
    title = lines[0][:120] if lines else "Research Project"
    lower = brief.lower()
    geographies = []
    for geography in ["New Jersey", "United States", "PJM", "county", "state", "municipality", "national"]:
        if geography.lower() in lower:
            geographies.append(geography)
    methods = [method for method in ["difference-in-differences", "econometric modeling", "spatial analysis", "regression", "simulation"] if method in lower]
    deliverables = [item for item in ["technical report", "presentation deck", "data workbook", "dashboard"] if item in lower]
    source_hints = []
    for source in ["PJM", "NOAA", "Census", "ACS", "FERC", "EIA", "BLS", "FRED", "World Bank", "NJDEP", "NJBPU"]:
        if source.lower() in lower:
            source_hints.append(source)
    return {
        "title": title,
        "summary": lines[1][:280] if len(lines) > 1 else "",
        "audience": _match_after_phrase(brief, "inform"),
        "objective": _extract_sectionish(brief, "objective") or title,
        "causal_questions": _bulletish(brief, ["how", "do", "what"]),
        "outcomes": _match_keywords(brief, ["cost", "price", "rate", "load", "congestion", "volatility", "forecast"]),
        "units_of_analysis": _match_keywords(brief, ["data center", "load zone", "municipality", "county", "utility", "ratepayer"]),
        "geographies": geographies,
        "time_windows": re.findall(r"\b20\d{2}\s*[–-]\s*20\d{2}\b", brief),
        "methods": methods,
        "deliverables": deliverables,
        "controls": _match_keywords(brief, ["weather", "temperature", "population", "income", "economic growth", "utility investment"]),
        "entities": _match_keywords(brief, ["data center", "load zone", "forecast", "consumer", "grid", "transmission constraint", "utility"]),
        "measures": _match_keywords(brief, ["electricity costs", "locational marginal prices", "demand", "capacity", "congestion costs"]),
        "source_hints": source_hints,
    }


def _extract_sectionish(brief: str, keyword: str) -> str:
    pattern = re.compile(rf"{keyword}.*?(?=\n[A-Z][^.:\n]+:|\Z)", re.IGNORECASE | re.DOTALL)
    match = pattern.search(brief)
    return re.sub(r"\s+", " ", match.group(0)).strip()[:500] if match else ""


def _bulletish(brief: str, starters: list[str]) -> list[str]:
    results = []
    for line in brief.splitlines():
        stripped = line.strip(" -•\t")
        if any(stripped.lower().startswith(prefix) for prefix in starters):
            results.append(stripped[:180])
    return _dedupe(results[:6])


def _match_keywords(brief: str, keywords: list[str]) -> list[str]:
    lower = brief.lower()
    return [keyword.title() for keyword in keywords if keyword.lower() in lower]


def _match_after_phrase(brief: str, phrase: str) -> str:
    idx = brief.lower().find(phrase.lower())
    if idx == -1:
        return ""
    return re.sub(r"\s+", " ", brief[idx : idx + 240]).strip()


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _dedupe_title_case(values: list[str]) -> list[str]:
    normalized = []
    for value in values:
        cleaned = re.sub(r"[^A-Za-z0-9]+", " ", value).strip()
        if not cleaned:
            continue
        normalized.append("".join(part.capitalize() for part in cleaned.split()))
    return _dedupe(normalized)


def _draft_source_yaml(slug: str, name: str, readiness: str) -> str:
    return "\n".join(
        [
            f"name: {slug}",
            "type: api",
            "url: https://example.com/review-required",
            "response_format: json",
            "description: |",
            f"  Draft source for review: {name}",
            f"  Readiness: {readiness}",
            "fields:",
            "  - source: id",
            "    alias: id",
            "  - source: value",
            "    alias: value",
        ]
    )


def _current_plan_md(project: dict[str, Any], graph: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    source_summary = summarize_readiness(sources)
    next_steps = [
        "- Review proposed ontology classes and source coverage.",
        "- Confirm draft or manual-review sources before hydration.",
        "- Approve hydration once the source set is acceptable.",
    ]
    return textwrap.dedent(
        f"""\
        # Current Plan

        Project: {project['name']}

        ## Objective

        {graph.get('objective') or graph.get('summary') or 'Define the first approved plan for this project.'}

        ## Source Readiness

        - Ready: {source_summary.get(READY, 0)}
        - Draft for review: {source_summary.get(DRAFT, 0)}
        - Missing or manual: {source_summary.get(MISSING, 0)}

        ## Next Steps

        {"\n".join(next_steps)}
        """
    )


def _task_board_md(sources: list[dict[str, Any]]) -> str:
    ready = [source["name"] for source in sources if source["readiness"] == READY]
    review = [source["name"] for source in sources if source["readiness"] != READY]
    ready_items = "\n".join(f"- Validate source coverage for {name}" for name in ready[:5]) or "None yet."
    review_items = "\n".join(f"- Review source draft for {name}" for name in review[:5]) or "None."
    return textwrap.dedent(
        f"""\
        # Task Board

        ## Backlog

        - Confirm the generated research scope and success criteria

        ## Ready

        {ready_items}

        ## Awaiting Approval

        {review_items}

        ## Running

        None.

        ## Blocked

        None.

        ## Review

        None.

        ## Done

        None.
        """
    )


def _brief_topic_md(graph: dict[str, Any]) -> str:
    return textwrap.dedent(
        f"""\
        # Brief Summary

        ## Audience

        {graph.get('audience') or 'Not specified.'}

        ## Objective

        {graph.get('objective') or 'Not specified.'}

        ## Methods

        {', '.join(graph.get('methods') or []) or 'Not specified.'}

        ## Deliverables

        {', '.join(graph.get('deliverables') or []) or 'Not specified.'}
        """
    )


def _source_notes_md(sources: list[dict[str, Any]]) -> str:
    lines = ["# Source Notes", ""]
    for source in sources:
        lines.extend(
            [
                f"## {source['name']}",
                "",
                f"- Readiness: `{source['readiness']}`",
                f"- Provider: `{source['provider']}`",
                f"- Reason: {source['reason']}",
                f"- Description: {source['description']}",
                "",
            ]
        )
    return "\n".join(lines)
