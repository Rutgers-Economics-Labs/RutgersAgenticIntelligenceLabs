"""
Resolve pipeline + referenced Convex configs and run validate_pipeline_runnable.

Where validation runs:
  • POST /api/v1/configs/pipelines/validate — body ``{"content": "<pipeline yaml>"}``;
    returns ``{valid, errors}`` (used by the web Configs editor for pipelines).
  • POST/PUT /api/v1/configs/pipelines — same checks before save.
  • POST /api/v1/jobs — before a job is queued (422 with ``detail: string[]`` on failure).
  • ``hydration_worker.run`` — runs the same ``validate_pipeline_runnable`` check again
    after the job is marked running, logs a ``[preflight]`` section to Convex job logs,
    then proceeds (catches registry drift and surfaces wiring on the log page).
  • ``validate_pipeline_runnable`` in ``app.services.yaml_service`` — pure Python checks
    (classes, foreach order, transforms) when you have YAML strings without Convex.

Project/agent tools that call ``_trigger_job`` use ``ensure_pipeline_ready`` here and
return structured errors if validation fails.
"""
from app.core.config import settings
from app.services.yaml_service import parse, validate_pipeline_runnable


class PipelineValidationFailed(Exception):
    """Raised when validate_stored_pipeline finds blocking issues."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Pipeline validation failed ({len(errors)} issue(s))")


async def ensure_pipeline_ready(convex, pipeline: dict) -> None:
    err = await validate_stored_pipeline(convex, pipeline)
    if err:
        raise PipelineValidationFailed(err)


async def validate_stored_pipeline(convex, pipeline: dict) -> list[str]:
    """
    `pipeline` is a Convex document with at least `content` and usually
    `parsedSpec` / `referencedApiSlugs`.
    """
    content = pipeline.get("content") or ""
    parsed = pipeline.get("parsedSpec") or {}
    if not parsed and content.strip():
        try:
            parsed = parse(content)
        except ValueError:
            parsed = {}

    api_slugs: list[str] = list(pipeline.get("referencedApiSlugs") or [])
    if not api_slugs and parsed.get("steps"):
        api_slugs = list(
            {s["api"] for s in parsed["steps"] if isinstance(s, dict) and s.get("api")}
        )

    api_yaml_by_slug: dict[str, str] = {}
    for slug in api_slugs:
        row = await convex.query("configs:getApi", {"slug": slug})
        if row:
            api_yaml_by_slug[slug] = row["content"]

    onto_ref = str(parsed.get("ontology", "core") or "core").strip() or "core"
    onto_yaml: str | None = None
    onto_row = await convex.query("configs:getOntology", {"slug": onto_ref})
    if onto_row:
        onto_yaml = onto_row["content"]

    xf = settings.engine_root / "transforms"
    transform_dir = xf if xf.is_dir() else None

    more = validate_pipeline_runnable(
        content,
        api_yaml_by_slug,
        ontology_yaml=onto_yaml,
        engine_root=settings.engine_root,
        transform_dir=transform_dir,
    )
    return more
