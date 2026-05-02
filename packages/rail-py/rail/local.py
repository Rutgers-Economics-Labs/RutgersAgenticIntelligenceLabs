from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

from rail.manifest import RailManifest, load_manifest


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

    def read_rail_yaml(self) -> RailManifest:
        self._manifest = load_manifest(self.project_path)
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
        from engine.pipeline_runner import run_pipeline

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
            return {
                "status": "reused",
                "pipeline_slug": resolved_slug,
                "artifact_db_path": str(self.artifact_db_path),
                "artifact_duckdb_path": str(self.artifact_duckdb_path),
            }

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
            run_pipeline(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)

        # Record meta for future reuse checks
        self._write_hydration_meta(resolved_slug, hydration_mode)

        return {
            "status": "hydrated",
            "pipeline_slug": resolved_slug,
            "artifact_db_path": str(self.artifact_db_path),
            "artifact_duckdb_path": str(self.artifact_duckdb_path),
        }

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
        from rail.integrity import ResearchIntegrityRepo
        repo = ResearchIntegrityRepo(self.project_path)
        return repo.load_all().model_dump(mode="json")

    def get_integrity_assumptions(self, project_slug: str) -> list[dict]:
        from rail.integrity import ResearchIntegrityRepo
        repo = ResearchIntegrityRepo(self.project_path)
        return [item.model_dump(mode="json") for item in repo.load_assumptions()]

    def get_integrity_sources(self, project_slug: str) -> list[dict]:
        from rail.integrity import ResearchIntegrityRepo
        repo = ResearchIntegrityRepo(self.project_path)
        return [item.model_dump(mode="json") for item in repo.load_sources()]

    def get_integrity_claims(self, project_slug: str) -> list[dict]:
        from rail.integrity import ResearchIntegrityRepo
        repo = ResearchIntegrityRepo(self.project_path)
        return [item.model_dump(mode="json") for item in repo.load_claims()]

    def get_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        return {"error": "rerun plan generation is currently only available via cloud API"}

    def apply_integrity_rerun_plan(self, project_slug: str, assumption_key: str) -> dict:
        return {"error": "rerun plan application is currently only available via cloud API"}
