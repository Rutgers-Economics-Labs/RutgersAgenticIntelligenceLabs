import re

with open('packages/api/app/routers/sql.py', 'r') as f:
    content = f.read()

content = content.replace(
    '''@router.get("/schema")
async def get_schema(project_id: str | None = Query(None, alias="projectId"), artifact_rev: str | None = Query(None, alias="artifactRev")):
    """Return DuckDB schema: {table: [{name, type}]}."""
    duck = None
    if project_id:
        art = await project_artifacts_service.resolve(project_id, artifact_rev)
        duck = art.duckdb_path
    return sql_service.get_schema(duckdb_path=duck)''',
    '''@router.get("/schema")
async def get_schema(project_id: str | None = Query(None, alias="projectId"), artifact_rev: str | None = Query(None, alias="artifactRev")):
    """Return DuckDB schema: {table: [{name, type, coverage: ...}]}."""
    duck = None
    if project_id:
        art = await project_artifacts_service.resolve(project_id, artifact_rev)
        duck = art.duckdb_path

    schema = sql_service.get_schema(duckdb_path=duck)
    from app.services import coverage_service
    coverage = await coverage_service.get_project_coverage(project_id=project_id)

    result = {}
    for table, cols in schema.items():
        table_coverage = coverage.get(table, {})
        row_count = table_coverage.get("row_count", 0)
        enriched_cols = []
        for col in cols:
            density = table_coverage.get("property_density", {}).get(col["name"], 0)
            enriched_cols.append({
                "name": col["name"],
                "type": col["type"],
                "density": density
            })
        result[table] = {
            "columns": enriched_cols,
            "row_count": row_count
        }
    return result'''
)

with open('packages/api/app/routers/sql.py', 'w') as f:
    f.write(content)
