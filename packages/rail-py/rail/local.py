import sys
from pathlib import Path
import yaml

class LocalEngine:
    def __init__(self, project_path: str, engine_path: str | None = None):
        self.project_path = Path(project_path).resolve()

        # Find engine — either explicit or by traversing up to monorepo
        if engine_path:
            self.engine_path = Path(engine_path).resolve()
        else:
            # Try monorepo layout: project is in packages/engine, we're at packages/rail-py
            candidate = Path(__file__).parent.parent.parent / "engine"
            self.engine_path = candidate if candidate.exists() else None

        if self.engine_path:
            sys.path.insert(0, str(self.engine_path))

    def read_rail_yaml(self) -> dict:
        rail_yaml = self.project_path / "rail.yaml"
        if not rail_yaml.exists():
            raise FileNotFoundError(f"rail.yaml not found in {self.project_path}")
        return yaml.safe_load(rail_yaml.read_text())

    def hydrate(self, pipeline_slug: str) -> dict:
        from engine.pipeline_runner import run_pipeline
        pipeline_path = self.project_path / f"configs/pipelines/{pipeline_slug}.yaml"
        return run_pipeline(str(pipeline_path))

    def query_sql(self, sql: str) -> dict:
        import duckdb
        onto_duckdb = self.project_path / "ontology/onto.duckdb"
        conn = duckdb.connect(str(onto_duckdb), read_only=True)
        result = conn.execute(sql).fetchdf()
        conn.close()
        return {"columns": list(result.columns), "rows": result.values.tolist()}

    def get_classes(self) -> list[dict]:
        import duckdb
        onto_duckdb = self.project_path / "ontology/onto.duckdb"
        conn = duckdb.connect(str(onto_duckdb), read_only=True)
        tables = conn.execute("SHOW TABLES").fetchdf()
        classes = []
        for t in tables["name"]:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            classes.append({"name": t, "instance_count": count})
        conn.close()
        return classes