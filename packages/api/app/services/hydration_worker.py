"""
Runs a hydration job as a subprocess, streams stdout to Convex jobLogs,
and updates job/step status in real time.
"""
import asyncio
import logging
import os
import re
import sys
import tempfile
import time
from typing import Union
from pathlib import Path

import yaml

from app.core.config import settings
from app.services.convex_client import convex
from app.services.storage_service import storage
from app.services.yaml_service import parse as parse_config_yaml, validate_pipeline_runnable

logger = logging.getLogger("rail.hydration")

# Patterns from pipeline_runner.py print() calls
_STEP_START = re.compile(r"\[step\] (.+?):")
_STEP_DONE  = re.compile(r"-> (\d+) (\w+) individuals processed")
_CACHE_LINE = re.compile(r"\[cache\]")
_FETCH_LINE = re.compile(r"\[fetch\]")
_SKIP_LINE  = re.compile(r"\[skip\]")


async def run(job_id: str, pipeline_content: str, api_configs: dict[str, str], onto_configs: dict[str, str] = None):
    """
    Execute a hydration job end-to-end.

    pipeline_content: raw YAML string of the pipeline config
    api_configs: {slug: yaml_content} for all API configs referenced by the pipeline
    onto_configs: {slug: yaml_content} for any ontology configs referenced
    """
    onto_configs = onto_configs or {}
    seq_holder = [0]

    async def emit(
        level: str,
        message: str,
        step: Union[str, None] = None,
    ) -> None:
        seq_holder[0] += 1
        await _log(job_id, level, message, seq=seq_holder[0], step=step)

    logger.info("[%s] Hydration job starting (%d API config(s), %d ontology override(s))", job_id, len(api_configs), len(onto_configs))
    await _update_job(job_id, {"status": "running", "startedAt": int(time.time() * 1000)})
    await emit("info", "[job] Starting hydration — pre-flight validation, then engine run")

    try:
        # ── Pre-flight: same checks as API enqueue, logged to Convex for the job detail page ──
        await emit("info", "[preflight] Checking pipeline ↔ ontology ↔ data sources (wiring)")
        try:
            pipe_spec = parse_config_yaml(pipeline_content)
        except ValueError as e:
            await emit("error", f"[preflight] Invalid pipeline YAML: {e}")
            raise RuntimeError(f"Invalid pipeline YAML: {e}") from e

        steps = pipe_spec.get("steps") or []
        onto_ref = str(pipe_spec.get("ontology", "core") or "core")
        step_api_slugs = [
            s["api"] for s in steps if isinstance(s, dict) and s.get("api")
        ]

        await emit("info", f"[preflight] Ontology ref: {onto_ref!r}")
        if onto_ref in onto_configs:
            await emit("info", "[preflight] Ontology source: Convex (stored ontology config)")
        else:
            fp = settings.engine_root / "configs" / "ontology" / f"{onto_ref}.yaml"
            if not fp.is_file():
                fp = settings.engine_root / "configs" / "ontology" / "core.yaml"
            await emit(
                "info",
                f"[preflight] Ontology source: engine package ({fp.name}) under {settings.engine_root / 'configs' / 'ontology'}",
            )

        await emit("info", f"[preflight] Pipeline steps: {len(steps)}")
        for i, s in enumerate(steps):
            if not isinstance(s, dict):
                await emit("warn", f"[preflight]   Step {i + 1}: skipped (not a mapping)")
                continue
            await emit(
                "info",
                f"[preflight]   Step {i + 1}: name={s.get('name')!r} api={s.get('api')!r} "
                f"class={s.get('class')!r} uri_template={s.get('uri')!r}",
            )

        await emit("info", f"[preflight] API configs attached to this job: {sorted(api_configs.keys())}")
        missing_apis = [slug for slug in step_api_slugs if slug not in api_configs]
        if missing_apis:
            for slug in missing_apis:
                await emit(
                    "error",
                    f"[preflight] Step references api={slug!r} but no YAML was loaded (missing in Convex or referencedApiSlugs)",
                )
            raise RuntimeError(f"Missing API configs for: {missing_apis}")

        for slug, raw in api_configs.items():
            try:
                spec = yaml.safe_load(raw) or {}
            except yaml.YAMLError as e:
                await emit("error", f"[preflight] API {slug!r}: invalid YAML — {e}")
                raise RuntimeError(f"API config {slug!r} has invalid YAML") from e
            st = spec.get("type", "api")
            nm = spec.get("name", slug)
            await emit(
                "info",
                f"[preflight]   Data source {slug!r}: type={st!r} config_name={nm!r}",
            )

        onto_yaml = onto_configs.get(onto_ref)
        transform_dir = settings.engine_root / "transforms"
        pf_errors = validate_pipeline_runnable(
            pipeline_content,
            api_configs,
            ontology_yaml=onto_yaml,
            engine_root=settings.engine_root,
            transform_dir=transform_dir if transform_dir.is_dir() else None,
        )
        if pf_errors:
            await emit("error", "[preflight] Validation failed — details:")
            for err in pf_errors:
                await emit("error", f"[preflight]   • {err}")
            raise RuntimeError(
                "Pre-flight validation failed — fix pipeline, ontology, or API configs and re-run."
            )

        await emit(
            "info",
            "[preflight] OK — steps, foreach order, ontology classes/properties, and transforms line up.",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Materialize all config files the engine expects on disk
            api_dir = tmpdir / "configs" / "apis"
            onto_dir = tmpdir / "configs" / "ontology"
            pipeline_dir = tmpdir / "configs" / "pipelines"
            api_dir.mkdir(parents=True)
            onto_dir.mkdir(parents=True)
            pipeline_dir.mkdir(parents=True)

            await emit("info", f"[setup] Workspace: {tmpdir}")

            # Write API configs and resolve storage keys
            for slug, content in api_configs.items():
                api_spec = yaml.safe_load(content)
                
                # If this API uses an uploaded file, download it
                if api_spec.get("type") == "uploaded" and "storage_key" in api_spec:
                    storage_key = api_spec["storage_key"]
                    filename = Path(storage_key).name
                    local_data_path = tmpdir / "sources" / filename
                    local_data_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    await emit("info", f"  [setup] Downloading uploaded data: {filename}")
                    await storage.download(storage_key, local_data_path)
                    
                    # Update the spec to point to the local file for the engine
                    api_spec["path"] = str(local_data_path)

                if api_spec.get("type") in {"pdf", "docx"} and "storage_key" in api_spec and "path" not in api_spec:
                    storage_key = api_spec["storage_key"]
                    filename = Path(storage_key).name
                    local_doc_path = tmpdir / "sources" / filename
                    local_doc_path.parent.mkdir(parents=True, exist_ok=True)

                    await emit("info", f"  [setup] Downloading document: {filename}")
                    await storage.download(storage_key, local_doc_path)
                    api_spec["path"] = str(local_doc_path)
                
                out_api = api_dir / f"{slug}.yaml"
                out_api.write_text(yaml.dump(api_spec))
                await emit(
                    "info",
                    f"[setup] Wrote {out_api.relative_to(tmpdir)} (type={api_spec.get('type', 'api')!r})",
                )

            # Rewrite pipeline YAML to point at the temp config paths
            pipeline_spec = yaml.safe_load(pipeline_content)

            # Resolve ontology config
            onto_ref = pipeline_spec.get("ontology", "core")
            if onto_ref in onto_configs:
                # Use user-provided ontology from Convex
                onto_path = onto_dir / f"{onto_ref}.yaml"
                onto_path.write_text(onto_configs[onto_ref])
                pipeline_spec["ontology"] = str(onto_path)
                await emit("info", f"[setup] Ontology YAML → {onto_path.relative_to(tmpdir)} (from Convex)")
            else:
                # Fall back to engine defaults
                engine_onto = settings.engine_root / "configs" / "ontology" / f"{onto_ref}.yaml"
                if not engine_onto.exists():
                    engine_onto = settings.engine_root / "configs" / "ontology" / "core.yaml"
                
                if engine_onto.exists():
                    import shutil
                    shutil.copy2(engine_onto, onto_dir / "core.yaml")
                    pipeline_spec["ontology"] = str(onto_dir / "core.yaml")
                    await emit(
                        "info",
                        f"[setup] Ontology copied from engine: {engine_onto} → {onto_dir / 'core.yaml'}",
                    )

            output_owl = str(tmpdir / "populated_ontology.owl")
            output_db  = str(tmpdir / "onto.db")
            pipeline_spec["output_owl"] = output_owl
            pipeline_spec["db"]         = output_db

            pipeline_path = pipeline_dir / "pipeline.yaml"
            pipeline_path.write_text(yaml.dump(pipeline_spec))
            await emit("info", f"[setup] Pipeline file: {pipeline_path.relative_to(tmpdir)}")

            # Also copy sources/ (CSVs etc.) into tmpdir if needed
            sources_src = settings.engine_root / "sources"
            if sources_src.exists():
                import shutil
                shutil.copytree(sources_src, tmpdir / "sources", dirs_exist_ok=True)
                await emit("info", f"[setup] Copied engine sources/ → {tmpdir / 'sources'}")

            cli_script = settings.engine_root / "engine" / "pipeline_runner_cli.py"
            py = sys.executable
            env = {
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    [str(settings.engine_root)]
                    + ([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])
                ),
                "RAIL_CACHE_DIR":      str(tmpdir / "cache"),
                "RAIL_API_CONFIG_DIR": str(api_dir),
                "RAIL_TRANSFORM_DIR":  str(settings.engine_root / "transforms"),
                "RAIL_ANALYSIS_DIR":   str(settings.engine_root / "analysis"),
                "FRED_API_KEY":        settings.fred_api_key,
            }

            fred_set = "yes" if (settings.fred_api_key or "").strip() else "no"
            await emit(
                "info",
                f"[job] Environment: RAIL_API_CONFIG_DIR={api_dir} RAIL_CACHE_DIR={tmpdir / 'cache'} "
                f"RAIL_TRANSFORM_DIR={settings.engine_root / 'transforms'} FRED_API_KEY_set={fred_set}",
            )
            await emit(
                "info",
                f"[job] Spawning engine: {py} {cli_script} (cwd={tmpdir}, PYTHONPATH includes engine root)",
            )
            logger.info("[%s] subprocess: %s %s %s", job_id, py, cli_script, pipeline_path)

            proc = await asyncio.create_subprocess_exec(
                py,
                str(cli_script),
                str(pipeline_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(tmpdir),
                env=env,
            )

            current_step = None
            line_count = 0
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                line_count += 1
                level = "warn" if "warning" in line.lower() else (
                    "error" if "error" in line.lower() or "traceback" in line.lower() else "info"
                )

                m = _STEP_START.search(line)
                if m:
                    current_step = m.group(1).strip()
                    await _update_step(job_id, current_step, "running")

                m = _STEP_DONE.search(line)
                if m and current_step:
                    await _update_step(job_id, current_step, "done", row_count=int(m.group(1)))
                    current_step = None

                seq_holder[0] += 1
                await _log(job_id, level, line, seq=seq_holder[0], step=current_step)

            rc = await proc.wait()
            await emit("info", f"[job] Engine process finished (exit code {rc}, {line_count} stdout line(s))")
            logger.info("[%s] subprocess exit=%s lines=%s", job_id, rc, line_count)

            if rc != 0:
                raise RuntimeError(
                    f"hydration process exited with code {rc} "
                    f"(see log lines above for Python traceback or engine output)"
                )

            # Upload artifacts
            db_key  = await storage.upload(job_id, "onto.db",  output_db)
            owl_key = await storage.upload(job_id, "populated_ontology.owl", output_owl)

            await emit("info", f"[job] Done — quadstore: {db_key}")

            await _update_job(job_id, {
                "status": "success",
                "finishedAt": int(time.time() * 1000),
                "outputDbPath": db_key,
                "outputOwlPath": owl_key,
            })

            # Reload ontology cache with new quadstore
            from app.services import ontology_service, sql_service
            ontology_service.load(db_key)

            # Export to DuckDB for SQL queries
            try:
                duckdb_path = str(Path(db_key).parent / "onto.duckdb") if "/" in db_key else \
                              str(settings.engine_root / "ontology" / "onto.duckdb")
                await ontology_service.export_to_duckdb(duckdb_path)
                sql_service.set_path(duckdb_path)
                await emit("info", f"[job] DuckDB export ready: {duckdb_path}")
            except Exception as e:
                await emit("warn", f"[job] DuckDB export failed (non-fatal): {e}")

            try:
                from app.services import embedding_service

                await embedding_service.build_index(db_key)
                await emit("info", "[job] Semantic index ready")
            except Exception as e:
                await emit("warn", f"[job] Embedding index failed (non-fatal): {e}")

    except asyncio.CancelledError:
        # Uvicorn --reload, Ctrl+C, or process exit cancels background tasks — not an engine bug.
        msg = (
            "Hydration was interrupted (API server shutdown or hot-reload). "
            "With `uvicorn --reload`, saving Python files restarts the server and cancels in-flight jobs. "
            "For long hydrations, run without `--reload` (e.g. same command without `--reload`), "
            "or avoid editing the API package until the job finishes."
        )
        logger.warning("[%s] %s", job_id, msg)

        async def _persist_interrupted() -> None:
            await _update_job(
                job_id,
                {
                    "status": "failed",
                    "finishedAt": int(time.time() * 1000),
                    "errorMessage": msg,
                },
            )
            seq_holder[0] += 1
            await _log(job_id, "error", f"[job] {msg}", seq=seq_holder[0])

        try:
            await asyncio.shield(_persist_interrupted())
        except Exception:
            logger.exception("[%s] Could not persist interrupted state to Convex", job_id)
        raise

    except Exception as exc:
        logger.exception("[%s] Hydration job failed", job_id)
        await _update_job(job_id, {
            "status": "failed",
            "finishedAt": int(time.time() * 1000),
            "errorMessage": str(exc),
        })
        try:
            seq_holder[0] += 1
            await _log(job_id, "error", f"[job] Failed: {exc}", seq=seq_holder[0])
        except Exception:
            logger.exception("[%s] Could not append failure log to Convex", job_id)


async def _log(job_id: str, level: str, message: str, seq: int, step: Union[str, None] = None):
    text = f"[job {job_id[:8]}…] {message}"
    if level == "error":
        logger.error("%s", text)
    elif level == "warn":
        logger.warning("%s", text)
    else:
        logger.info("%s", text)
    try:
        await convex.mutation("jobs:appendLog", {
            "jobId": job_id,
            "seq": seq,
            "level": level,
            "message": message,
            "stepName": step,
            "timestamp": int(time.time() * 1000),
        })
    except Exception:
        logger.exception(
            "[%s] Convex appendLog failed (seq=%s) — UI may show no logs; message was: %s",
            job_id,
            seq,
            message[:500],
        )


async def _update_job(job_id: str, fields: dict):
    try:
        await convex.mutation("jobs:updateJob", {"jobId": job_id, **fields})
    except Exception:
        logger.exception("[%s] Convex updateJob failed fields=%s", job_id, list(fields.keys()))



async def _update_step(job_id: str, step_name: str, status: str, row_count: Union[int, None] = None):
    try:
        await convex.mutation("jobs:updateStep", {
            "jobId": job_id,
            "stepName": step_name,
            "status": status,
            "rowCount": row_count,
            "timestamp": int(time.time() * 1000),
        })
    except Exception:
        logger.exception("[%s] Convex updateStep failed step=%s status=%s", job_id, step_name, status)

