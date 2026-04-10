"""
Coverage service for RAIL.

Determines if a research question can be answered with the current project graph
or if new data sources need to be onboarded.
"""

from typing import Dict, Any, List
import duckdb

from app.services import sql_service
from app.services import registry_service
from app.services.agent_service import _resolve_duckdb_path


async def get_project_coverage(project_id: str | None = None) -> Dict[str, Any]:
    """
    Scans the DuckDB schema and returns a map of classes and their "density"
    (row counts, non-null property percentage).
    """
    coverage_map = {}
    try:
        # Resolve DuckDB path for the given project_id
        duckdb_path = None
        if project_id:
            duckdb_path = await _resolve_duckdb_path(project_id=project_id)

        # fallback to global if None
        if not duckdb_path:
            duckdb_path = str(sql_service.get_path() or "ontology/onto.duckdb")

        # Get the schema
        schema = sql_service.get_schema(duckdb_path=duckdb_path)

        # Connect to compute densities
        con = duckdb.connect(duckdb_path, read_only=True)
        try:
            for table_name, columns in schema.items():
                if table_name == "ontology_metadata":
                    continue

                # Count total rows
                count_query = f"SELECT COUNT(*) FROM {table_name}"
                total_rows = con.execute(count_query).fetchone()[0]

                if total_rows == 0:
                    coverage_map[table_name] = {
                        "row_count": 0,
                        "property_density": {}
                    }
                    continue

                # Calculate density for each column
                density = {}
                for col in columns:
                    col_name = col["name"]
                    # Query non-null count
                    non_null_query = f"SELECT COUNT(*) FROM {table_name} WHERE {col_name} IS NOT NULL"
                    non_null_count = con.execute(non_null_query).fetchone()[0]
                    density[col_name] = round(non_null_count / total_rows, 4)

                coverage_map[table_name] = {
                    "row_count": total_rows,
                    "property_density": density
                }
        finally:
            con.close()

    except Exception as e:
        # If the file doesn't exist or other DB error occurs
        return {"error": str(e)}

    return coverage_map


async def check_data_availability(ontology_classes: List[str], time_range: str | None = None, project_id: str | None = None) -> Dict[str, Any]:
    """
    Cross-references requested data with both the current DuckDB and the global dataSourceRegistry.
    """
    result = {
        "available_in_project": {},
        "missing_but_available_in_registry": [],
        "missing_and_unknown": []
    }

    # 1. Check current project coverage
    coverage = await get_project_coverage(project_id=project_id)

    # Check if there is an error
    if "error" in coverage:
        # DuckDB might not be initialized, treat all as missing
        pass

    for cls in ontology_classes:
        if cls in coverage and coverage[cls].get("row_count", 0) > 0:
            result["available_in_project"][cls] = coverage[cls]
        else:
            # 2. Search registry for missing classes
            # Simple keyword match for now
            registry_entries = await registry_service.search_registry_entries(query_text=cls)
            if registry_entries:
                result["missing_but_available_in_registry"].append({
                    "class": cls,
                    "potential_sources": registry_entries[:3] # Return top 3 matches
                })
            else:
                result["missing_and_unknown"].append(cls)

    return result
