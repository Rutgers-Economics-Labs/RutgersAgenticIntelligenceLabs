from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from rail.integrity import ResearchIntegrityRepo, sync_sources_from_configs
from rail.manifest import RailManifest, boot_validate_project


class LocalEngine:
    def __init__(self, project_path: str, engine_path: str | None = None):
        self.project_path = Path(project_path).resolve()
        self._manifest: RailManifest | None = None

        # Find engine — either explicit or by traversing up to monorepo
        if engine_path:
            self.engine_path = Path(engine_path).resolve()
        else:
            # Try monorepo layout: project is in packages/engine, we're at packages/rail-py
            candidate = Path(__file__).parent.parent.parent / "engine"
            self.engine_path = candidate if candidate.exists() else None

        if self.engine_path:
            sys.path.insert(0, str(self.engine_path))

    def _integrity_service_module(self):
        api_root = Path(__file__).parent.parent.parent / "api"
        api_root_str = str(api_root.resolve())
        if api_root_str in sys.path:
            sys.path.remove(api_root_str)
        sys.path.insert(0, api_root_str)
        return importlib.import_module("app.services.integrity_service")

    def read_rail_yaml(self) -> RailManifest:
        self._manifest = boot_validate_project(self.project_path)
        return self._manifest

    @property
    def manifest(self) -> RailManifest:
        if self._manifest is None:
            self._manifest = self.read_rail_yaml()
        return self._manifest

    # ── .ontology path alignment ──────────────────────────────────────────────

    @property
    def ontology_root(self) -> Path:
        """Resolved absolute path to the .ontology directory as declared in rail.yaml."""
        return (self.project_path / self.manifest.paths.ontology_root).resolve()

    @property
    def artifact_db_path(self) -> Path:
        """Path to the owlready2 quadstore (onto.db) inside the ontology root."""
        return self.ontology_root / "onto.db"

    @property
    def artifact_duckdb_path(self) -> Path:
        """Path to the DuckDB relational mirror (onto.duckdb) inside the ontology root."""
        return self.ontology_root / "onto.duckdb"

    # ── Reuse-aware hydration ─────────────────────────────────────────────────

    @property
    def _hydration_meta_path(self) -> Path:
        return self.ontology_root / ".rail_hydration.json"

    def _manifest_fingerprint(self) -> str:
        return hashlib.sha256(
            (self.project_path / "rail.yaml").read_bytes()
        ).hexdigest()

    def _repo_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.project_path), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() or None
        except Exception:
            return None

    def _read_hydration_meta(self) -> dict:
        path = self._hydration_meta_path
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _write_hydration_meta(self, pipeline_slug: str, hydration_mode: str) -> None:
        meta = {
            "manifest_fingerprint": self._manifest_fingerprint(),
            "commit_sha": self._repo_commit(),
            "pipeline_slug": pipeline_slug,
            "hydration_mode": hydration_mode,
        }
        self._hydration_meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._hydration_meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def _is_reusable(self, pipeline_slug: str, hydration_mode: str) -> bool:
        """Return True when an existing local artifact is valid and can be reused."""
        if not self.artifact_db_path.exists():
            return False
        meta = self._read_hydration_meta()
        if not meta:
            return False
        if meta.get("pipeline_slug") != pipeline_slug:
            return False
        if meta.get("hydration_mode") != hydration_mode:
            return False
        if meta.get("manifest_fingerprint") != self._manifest_fingerprint():
            return False
        current_commit = self._repo_commit()
        if current_commit and meta.get("commit_sha") != current_commit:
            return False
        return True

    # ── Hydration entrypoint ──────────────────────────────────────────────────

    def hydrate(self, pipeline_slug: str | None = None, *, force: bool = False) -> dict:
        """Run hydration for the given pipeline, or the manifest default.

        Skips execution and returns status="reused" when a valid local artifact
        already exists unless *force* is True.
        """
        manifest = self.manifest

        # ── Default hydration target resolution ───────────────────────────────
        resolved_slug = pipeline_slug or manifest.hydration.default_pipeline
        if not resolved_slug:
            raise ValueError(
                "pipeline_slug is required when rail.yaml does not define "
                "hydration.default_pipeline"
            )

        hydration_mode = manifest.hydration.hydration_mode or "full"

        # ── Reuse check ───────────────────────────────────────────────────────
        if not force and self._is_reusable(resolved_slug, hydration_mode):
            result = {
                "status": "reused",
                "pipeline_slug": resolved_slug,
                "artifact_db_path": str(self.artifact_db_path),
                "artifact_duckdb_path": str(self.artifact_duckdb_path),
            }
            self._record_hydration_lineage(resolved_slug)
            return result

        # ── .ontology path alignment for pipeline output ──────────────────────
        pipelines_dir = self.project_path / manifest.hydration.pipelines_dir
        pipeline_path = pipelines_dir / f"{resolved_slug}.yaml"
        if not pipeline_path.exists():
            raise FileNotFoundError(f"Pipeline YAML not found: {pipeline_path}")

        with open(pipeline_path) as f:
            pipeline_spec = yaml.safe_load(f)

        self.ontology_root.mkdir(parents=True, exist_ok=True)

        # Override output paths to be inside .ontology/
        pipeline_spec["db"] = str(self.artifact_db_path)
        pipeline_spec["output_owl"] = str(self.ontology_root / "populated_ontology.owl")
        pipeline_spec["duckdb"] = str(self.artifact_duckdb_path)

        # Resolve ontology reference relative to project root
        onto_ref = pipeline_spec.get("ontology")
        if onto_ref and not Path(onto_ref).is_absolute():
            candidate = (self.project_path / onto_ref).resolve()
            if candidate.exists():
                pipeline_spec["ontology"] = str(candidate)

        # Write a temporary pipeline YAML with the overridden paths
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, dir=self.ontology_root
        ) as tmp:
            yaml.dump(pipeline_spec, tmp)
            tmp_path = Path(tmp.name)

        try:
            from engine.pipeline_runner import run_pipeline
            previous_api_config_dir = os.environ.get("RAIL_API_CONFIG_DIR")
            previous_transform_dir = os.environ.get("RAIL_TRANSFORM_DIR")
            os.environ["RAIL_API_CONFIG_DIR"] = str(self.project_path / manifest.hydration.sources_dir)
            if manifest.hydration.transforms_dir:
                os.environ["RAIL_TRANSFORM_DIR"] = str(self.project_path / manifest.hydration.transforms_dir)
            run_pipeline(str(tmp_path))
        finally:
            if previous_api_config_dir is None:
                os.environ.pop("RAIL_API_CONFIG_DIR", None)
            else:
                os.environ["RAIL_API_CONFIG_DIR"] = previous_api_config_dir
            if previous_transform_dir is None:
                os.environ.pop("RAIL_TRANSFORM_DIR", None)
            else:
                os.environ["RAIL_TRANSFORM_DIR"] = previous_transform_dir
            tmp_path.unlink(missing_ok=True)

        # Record meta for future reuse checks
        self._write_hydration_meta(resolved_slug, hydration_mode)
        self._record_hydration_lineage(resolved_slug, pipeline_spec=pipeline_spec)

        return {
            "status": "hydrated",
            "pipeline_slug": resolved_slug,
            "artifact_db_path": str(self.artifact_db_path),
            "artifact_duckdb_path": str(self.artifact_duckdb_path),
        }

    def _record_hydration_lineage(self, pipeline_slug: str, *, pipeline_spec: dict | None = None) -> None:
        manifest = self.manifest
        repo = ResearchIntegrityRepo(self.project_path)
        if pipeline_spec is None:
            pipeline_path = self.project_path / manifest.hydration.pipelines_dir / f"{pipeline_slug}.yaml"
            if not pipeline_path.exists():
                return
            pipeline_spec = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
        source_keys = sorted(
            {
                *[str(item) for item in manifest.hydration.linked_sources],
                *[
                    str(step.get("api"))
                    for step in pipeline_spec.get("steps") or []
                    if isinstance(step, dict) and step.get("api")
                ],
            }
        )
        sync_sources_from_configs(
            self.project_path,
            sources_dir=manifest.hydration.sources_dir,
            source_keys=source_keys,
        )
        source_refs = [f"research_plan/state/sources.json#{source_key}" for source_key in source_keys]
        source_config_inputs = [
            str((Path(manifest.hydration.sources_dir) / f"{source_key}.yaml").as_posix())
            for source_key in source_keys
        ]
        pipeline_rel = str((Path(manifest.hydration.pipelines_dir) / f"{pipeline_slug}.yaml").as_posix())
        duckdb_rel = self.artifact_duckdb_path.relative_to(self.project_path).as_posix()
        hydration_meta_rel = self._hydration_meta_path.relative_to(self.project_path).as_posix()
        repo.upsert_artifact_lineage(
            {
                "artifact_path": duckdb_rel,
                "artifact_type": "dataset",
                "title": self.artifact_duckdb_path.name,
                "promotion_state": "draft",
                "inputs": source_config_inputs,
                "scripts": [pipeline_rel],
                "sources": source_refs,
            }
        )
        repo.upsert_artifact_lineage(
            {
                "artifact_path": hydration_meta_rel,
                "artifact_type": "dataset",
                "title": self._hydration_meta_path.name,
                "promotion_state": "draft",
                "inputs": source_config_inputs,
                "scripts": [pipeline_rel],
                "sources": source_refs,
                "reproducibility_mode": "deterministic",
            }
        )

    # ── Query helpers ─────────────────────────────────────────────────────────

    def query_sql(self, sql: str) -> dict:
        import duckdb
        conn = duckdb.connect(str(self.artifact_duckdb_path), read_only=True)
        result = conn.execute(sql).fetchdf()
        conn.close()
        return {"columns": list(result.columns), "rows": result.values.tolist()}

    def get_classes(self) -> list[dict]:
        import duckdb
        conn = duckdb.connect(str(self.artifact_duckdb_path), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchdf()
        classes = []
        for t in tables["name"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            classes.append({"name": t, "instance_count": count})
        conn.close()
        return classes

    # ── Integrity ─────────────────────────────────────────────────────────────

    def get_integrity_status(self, project_slug: str) -> dict:
        api_root = Path(__file__).parent.parent.parent / "api"
        api_root_str = str(api_root.resolve())
        if api_root_str in sys.path:
            sys.path.remove(api_root_str)
        sys.path.insert(0, api_root_str)
        command_center_service = importlib.import_module("app.services.command_center_service")
        status = command_center_service.list_project_integrity(
            {
                "_id": project_slug,
                "name": self.manifest.project.name,
                "slug": project_slug,
                "status": "ready",
                "localRepoPath": str(self.project_path),
                "defaultBranch": "main",
            }
        )
        return {
            **status,
            "mode": "local",
        }

    def get_integrity_assumptions(self, project_slug: str) -> list[dict]:
        from rail.integrity import ResearchIntegrityRepo
        repo = ResearchIntegrityRepo(self.project_path)
        return [item.model_dump(mode="json") for item in repo.load_assumptions()]

    def get_integrity_sources(self, project_slug: str) -> list[dict]:
        integrity_service = self._integrity_service_module()
        return integrity_service.list_source_summaries(self.project_path)

    def get_integrity_source_detail(self, project_slug: str, source_key: str) -> dict:
        integrity_service = self._integrity_service_module()
        detail = integrity_service.get_source_detail(self.project_path, source_key)
        return {
            **detail,
            "mode": "local",
        }

    def get_integrity_claims(self, project_slug: str) -> list[dict]:
        integrity_service = self._integrity_service_module()
        return integrity_service.list_claim_summaries(self.project_path)

    def get_integrity_source_candidates(self, project_slug: str) -> list[dict]:
        repo = ResearchIntegrityRepo(self.project_path)
        return [record.model_dump(mode="json") for record in repo.load_source_candidates()]

    def get_integrity_claim_candidates(self, project_slug: str) -> list[dict]:
        repo = ResearchIntegrityRepo(self.project_path)
        return [record.model_dump(mode="json") for record in repo.load_claim_candidates()]

    def get_integrity_entity_candidates(self, project_slug: str) -> list[dict]:
        repo = ResearchIntegrityRepo(self.project_path)
        return [record.model_dump(mode="json") for record in repo.load_entity_candidates()]

    def get_integrity_conflicts(self, project_slug: str) -> list[dict]:
        repo = ResearchIntegrityRepo(self.project_path)
        return [record.model_dump(mode="json") for record in repo.load_conflicts()]

    def get_integrity_claim_detail(self, project_slug: str, claim_key: str) -> dict:
        integrity_service = self._integrity_service_module()
        detail = integrity_service.get_claim_detail(self.project_path, claim_key)
        return {
            **detail,
            "mode": "local",
        }

    def get_integrity_artifact_lineage(self, project_slug: str) -> list[dict]:
        repo = ResearchIntegrityRepo(self.project_path)
        return [item.model_dump(mode="json") for item in repo.load_artifact_lineage()]

    def get_integrity_artifact_detail(self, project_slug: str, artifact_path: str) -> dict:
        integrity_service = self._integrity_service_module()
        detail = integrity_service.get_artifact_detail(
            self.project_path,
            artifact_path,
            manifest=self.manifest,
        )
        return {
            **detail,
            "mode": "local",
        }

    def get_integrity_dependency_graph(self, project_slug: str) -> dict:
        integrity_service = self._integrity_service_module()
        graph = integrity_service.get_integrity_dependency_graph(self.project_path)
        return {
            **graph,
            "mode": "local",
        }

    def get_integrity_stale_graph(self, project_slug: str) -> dict:
        integrity_service = self._integrity_service_module()
        graph = integrity_service.get_stale_dependency_graph(self.project_path)
        return {
            **graph,
            "mode": "local",
        }

    def get_integrity_verification_runs(self, project_slug: str) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        runs = [item.model_dump(mode="json") for item in repo.load_verification_runs()]
        status_counts: dict[str, int] = {}
        loop_type_counts: dict[str, int] = {}
        for row in runs:
            status = str(row.get("status") or "pending")
            status_counts[status] = status_counts.get(status, 0) + 1
            loop_type = str(row.get("loop_type") or "analysis_reproducibility")
            loop_type_counts[loop_type] = loop_type_counts.get(loop_type, 0) + 1
        return {
            "verificationRuns": runs,
            "summary": {
                "count": len(runs),
                "statusCounts": status_counts,
                "loopTypeCounts": loop_type_counts,
            },
            "mode": "local",
        }

    def get_integrity_benchmark(self, project_slug: str, *, retrieval_limit: int = 10) -> dict:
        integrity_service = self._integrity_service_module()
        result = integrity_service.evaluate_default_integrity_benchmark_corpus(
            self.project_path,
            retrieval_limit=retrieval_limit,
        )
        result["mode"] = "local"
        return result

    def get_integrity_compile(
        self,
        project_slug: str,
        *,
        write_files: bool = True,
        alignment_paths: list[str] | None = None,
    ) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        result = repo.compile_truth_report(
            write_files=write_files,
            alignment_paths=alignment_paths,
        )
        result["mode"] = "local"
        return result

    def get_integrity_retrieval(
        self,
        project_slug: str,
        query: str,
        *,
        limit: int = 10,
        artifact_types: list[str] | None = None,
        claim_statuses: list[str] | None = None,
        source_freshness: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_stale: bool = False,
        include_blocked: bool = False,
    ) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        result = repo.hybrid_retrieve(
            query,
            limit=limit,
            artifact_types=artifact_types,
            claim_statuses=claim_statuses,
            source_freshness=source_freshness,
            date_from=date_from,
            date_to=date_to,
            include_stale=include_stale,
            include_blocked=include_blocked,
        )
        result["mode"] = "local"
        return result

    def get_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        integrity_service = self._integrity_service_module()
        plan = integrity_service.build_rerun_plan(self.project_path, assumption_key)
        plan["mode"] = "local"
        return plan

    def apply_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        plan = self.get_integrity_rerun_plan(project_slug, assumption_key)
        return {
            "mode": "local",
            "createdTasks": [],
            "rerunPlan": plan,
            "warning": "Local mode does not create planner tasks automatically; run the proposed tasks manually.",
        }

    def apply_integrity_reproducibility_rerun(
        self,
        project_slug: str,
        outputs: dict[str, str],
        *,
        run_id: str = "rerun-verification",
        scope: str = "health",
    ) -> dict:
        integrity_service = self._integrity_service_module()

        result = integrity_service.apply_reproducibility_rerun(
            self.project_path,
            outputs,
            run_id=run_id,
            scope=scope,
        )
        result["mode"] = "local"
        return result

    def apply_integrity_freshness_evaluation(
        self,
        project_slug: str,
        *,
        as_of: str | None = None,
    ) -> dict:
        integrity_service = self._integrity_service_module()

        result = integrity_service.apply_source_freshness_policy(
            self.project_path,
            as_of=as_of,
        )
        result["mode"] = "local"
        return result

    def apply_integrity_artifact_promotion(
        self,
        project_slug: str,
        artifact_path: str,
        *,
        target_state: str,
    ) -> dict:
        integrity_service = self._integrity_service_module()
        if target_state in {"partially_verified", "verified"}:
            hydration_meta = self._read_hydration_meta()
            if not self.artifact_duckdb_path.exists() or not hydration_meta:
                raise ValueError(
                    "Trusted artifact promotion requires local hydrated ontology state before promotion."
                )
        manifest = load_manifest(self.project_path)
        result = integrity_service.promote_artifact(
            self.project_path,
            manifest,
            artifact_path,
            target_state=target_state,
        )
        result["mode"] = "local"
        return result

    def apply_integrity_source_candidate_promotion(
        self,
        project_slug: str,
        candidate_key: str,
        *,
        source_key: str | None = None,
        source_type: str | None = None,
    ) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        result = repo.promote_source_candidate(
            candidate_key,
            source_key=source_key,
            source_type=source_type,
        )
        result["mode"] = "local"
        return result

    def apply_integrity_claim_candidate_promotion(
        self,
        project_slug: str,
        candidate_key: str,
        *,
        claim_key: str | None = None,
        status: str | None = None,
        artifact_path: str | None = None,
    ) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        result = repo.promote_claim_candidate(
            candidate_key,
            claim_key=claim_key,
            status=status,
            artifact_path=artifact_path,
        )
        result["mode"] = "local"
        return result

    def apply_integrity_conflict_resolution(
        self,
        project_slug: str,
        conflict_key: str,
        *,
        status: str,
        favored_claim_key: str | None = None,
        explanation: str | None = None,
    ) -> dict:
        repo = ResearchIntegrityRepo(self.project_path)
        result = repo.resolve_conflict(
            conflict_key,
            status=status,
            favored_claim_key=favored_claim_key,
            explanation=explanation,
        )
        result["mode"] = "local"
        return result
