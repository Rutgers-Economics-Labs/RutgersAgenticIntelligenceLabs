"""
Runs a hydration job as a subprocess, streams stdout to Convex jobLogs,
and updates job/step status in real time.
"""
import asyncio
import os
import re
import tempfile
import time
from typing import Union
from pathlib import Path

import yaml

from app.core.config import settings
from app.services.convex_client import convex
from app.services.storage_service import storage

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
    await _update_job(job_id, {"status": "running", "startedAt": int(time.time() * 1000)})
    await _log(job_id, "info", "[job] Starting hydration", seq=0)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Materialize all config files the engine expects on disk
            api_dir = tmpdir / "configs" / "apis"
            onto_dir = tmpdir / "configs" / "ontology"
            pipeline_dir = tmpdir / "configs" / "pipelines"
            api_dir.mkdir(parents=True)
            onto_dir.mkdir(parents=True)
            pipeline_dir.mkdir(parents=True)

            # Write API configs and resolve storage keys
            for slug, content in api_configs.items():
                api_spec = yaml.safe_load(content)
                
                # If this API uses an uploaded file, download it
                if api_spec.get("type") == "uploaded" and "storage_key" in api_spec:
                    storage_key = api_spec["storage_key"]
                    filename = Path(storage_key).name
                    local_data_path = tmpdir / "sources" / filename
                    local_data_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    await _log(job_id, "info", f"  [setup] Downloading uploaded data: {filename}", seq=0)
                    await storage.download(storage_key, local_data_path)
                    
                    # Update the spec to point to the local file for the engine
                    api_spec["path"] = str(local_data_path)
                
                (api_dir / f"{slug}.yaml").write_text(yaml.dump(api_spec))

            # Rewrite pipeline YAML to point at the temp config paths
            pipeline_spec = yaml.safe_load(pipeline_content)

            # Resolve ontology config
            onto_ref = pipeline_spec.get("ontology", "core")
            if onto_ref in onto_configs:
                # Use user-provided ontology from Convex
                onto_path = onto_dir / f"{onto_ref}.yaml"
                onto_path.write_text(onto_configs[onto_ref])
                pipeline_spec["ontology"] = str(onto_path)
            else:
                # Fall back to engine defaults
                engine_onto = settings.engine_root / "configs" / "ontology" / f"{onto_ref}.yaml"
                if not engine_onto.exists():
                    engine_onto = settings.engine_root / "configs" / "ontology" / "core.yaml"
                
                if engine_onto.exists():
                    import shutil
                    shutil.copy2(engine_onto, onto_dir / "core.yaml")
                    pipeline_spec["ontology"] = str(onto_dir / "core.yaml")

            output_owl = str(tmpdir / "populated_ontology.owl")
            output_db  = str(tmpdir / "onto.db")
            pipeline_spec["output_owl"] = output_owl
            pipeline_spec["db"]         = output_db

            pipeline_path = pipeline_dir / "pipeline.yaml"
            pipeline_path.write_text(yaml.dump(pipeline_spec))

            # Also copy sources/ (CSVs etc.) into tmpdir if needed
            sources_src = settings.engine_root / "sources"
            if sources_src.exists():
                import shutil
                shutil.copytree(sources_src, tmpdir / "sources", dirs_exist_ok=True)

            env = {
                **os.environ,
                "RAIL_CACHE_DIR":      str(tmpdir / "cache"),
                "RAIL_API_CONFIG_DIR": str(api_dir),
                "RAIL_TRANSFORM_DIR":  str(settings.engine_root / "transforms"),
                "RAIL_ANALYSIS_DIR":   str(settings.engine_root / "analysis"),
                "FRED_API_KEY":        settings.fred_api_key,
            }

            proc = await asyncio.create_subprocess_exec(
                "python", str(settings.engine_root / "engine" / "pipeline_runner_cli.py"),
                str(pipeline_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(tmpdir),
                env=env,
            )

            seq = 1
            current_step = None
            async for raw_line in proc.stdout:
                line = raw_line.decode(errors="replace").rstrip()
                level = "error" if "error" in line.lower() or "warning" in line.lower() else "info"

                m = _STEP_START.search(line)
                if m:
                    current_step = m.group(1).strip()
                    await _update_step(job_id, current_step, "running")

                m = _STEP_DONE.search(line)
                if m and current_step:
                    await _update_step(job_id, current_step, "done", row_count=int(m.group(1)))
                    current_step = None

                await _log(job_id, level, line, seq=seq, step=current_step)
                seq += 1

            await proc.wait()

            if proc.returncode != 0:
                raise RuntimeError(f"hydration process exited with code {proc.returncode}")

            # Upload artifacts
            db_key  = await storage.upload(job_id, "onto.db",  output_db)
            owl_key = await storage.upload(job_id, "populated_ontology.owl", output_owl)

            await _log(job_id, "info", f"[job] Done — quadstore: {db_key}", seq=seq)

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
                await _log(job_id, "info", f"[job] DuckDB export ready: {duckdb_path}", seq=seq)
            except Exception as e:
                await _log(job_id, "warn", f"[job] DuckDB export failed (non-fatal): {e}", seq=seq)

    except Exception as exc:
        await _update_job(job_id, {
            "status": "failed",
            "finishedAt": int(time.time() * 1000),
            "errorMessage": str(exc),
        })
        await _log(job_id, "error", f"[job] Failed: {exc}", seq=9999)


async def _log(job_id: str, level: str, message: str, seq: int, step: Union[str, None] = None):
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
        pass  # log failures must never crash the worker


async def _update_job(job_id: str, fields: dict):
    await convex.mutation("jobs:updateJob", {"jobId": job_id, **fields})


async def _update_step(job_id: str, step_name: str, status: str, row_count: Union[int, None] = None):
    await convex.mutation("jobs:updateStep", {
        "jobId": job_id,
        "stepName": step_name,
        "status": status,
        "rowCount": row_count,
        "timestamp": int(time.time() * 1000),
    })
