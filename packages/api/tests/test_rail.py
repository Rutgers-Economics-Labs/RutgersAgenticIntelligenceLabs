import rail
import pytest
import duckdb
import os
import yaml
from pathlib import Path

def test_cloud_acceptance(respx_mock):
    # Mock the API endpoints
    base_url = "http://localhost:8000/api/v1"

    # query
    respx_mock.post(f"{base_url}/sql").respond(
        json={"columns": ["count"], "rows": [[10]]}
    )

    # classes
    respx_mock.get(f"{base_url}/ontology/classes").respond(
        json=[{"name": "County", "instance_count": 10}]
    )

    # execute
    respx_mock.post(f"{base_url}/execute").respond(
        json={"stdout": "hello", "stderr": "", "dataframes": {}, "figures": [], "error": None}
    )

    p = rail.connect("nj-economics")

    import pandas as pd
    df = p.query("SELECT COUNT(*) FROM County")
    assert isinstance(df, pd.DataFrame)
    assert df["count"].iloc[0] == 10

    classes = p.classes()
    assert len(classes) == 1
    assert classes[0]["name"] == "County"

    res = p.execute("print(sql('SELECT * FROM State LIMIT 5'))")
    assert res["stdout"] == "hello"

def test_local_acceptance(tmp_path):
    project_dir = tmp_path / "nj-economics"
    project_dir.mkdir()

    rail_yaml = project_dir / "rail.yaml"
    with open(rail_yaml, "w") as f:
        yaml.dump({"slug": "nj-economics"}, f)

    ontology_dir = project_dir / "ontology"
    ontology_dir.mkdir()

    db_path = ontology_dir / "onto.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("CREATE TABLE County(id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO County VALUES (1, 'Bergen'), (2, 'Essex')")
    conn.close()

    p = rail.local(str(project_dir))

    df = p.query("SELECT COUNT(*) as count FROM County")
    assert df["count"].iloc[0] == 2

    classes = p.classes()
    assert any(c["name"] == "County" for c in classes)