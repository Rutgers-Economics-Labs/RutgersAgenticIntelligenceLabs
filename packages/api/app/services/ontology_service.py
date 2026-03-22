"""
Loads the OWL quadstore and answers queries against it.
The onto object is cached in memory; swapped out when a new hydration job completes.
"""
import asyncio
from pathlib import Path
from threading import Lock
from typing import Any, Union, List

from owlready2 import World, ObjectProperty

_onto = None
_world = None
_db_path: Union[str, None] = None
_lock = Lock()
# Executor ensures owlready2 SQLite access is single-threaded
_executor = None


def _get_executor():
    global _executor
    import concurrent.futures
    if _executor is None:
        _executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    return _executor


def load(db_path: Union[str, Path]):
    """Load (or reload) the quadstore from db_path. Thread-safe."""
    global _onto, _world, _db_path
    db_path = str(db_path)
    with _lock:
        if _world is not None:
            _world.close()
        _world = World()
        _world.set_backend(filename=db_path, exclusive=False)
        _onto = _world.get_ontology("http://example.org/rutgers_ontology.owl").load()
        _db_path = db_path


def _require_onto():
    if _onto is None:
        raise RuntimeError("Ontology not loaded. Run a hydration job first.")
    return _onto


def get_db_path() -> Union[str, None]:
    return _db_path


async def _run(fn, *args, **kwargs):
    """Run a sync ontology function in the dedicated thread executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(), lambda: fn(*args, **kwargs))


# ---------------------------------------------------------------------------
# Query functions (all sync; call via _run() from async endpoints)
# ---------------------------------------------------------------------------

def list_classes() -> list[dict]:
    onto = _require_onto()
    return sorted(
        [
            {"name": cls.name, "instanceCount": len(list(cls.instances()))}
            for cls in onto.classes()
        ],
        key=lambda c: c["name"],
    )


def list_instances(
    class_name: str,
    page: int = 1,
    limit: int = 50,
    search: str = "",
) -> dict:
    onto = _require_onto()
    cls = next((c for c in onto.classes() if c.name == class_name), None)
    if cls is None:
        raise ValueError(f"Class '{class_name}' not found in ontology")
    instances = list(cls.instances())
    if search:
        s = search.lower()
        instances = [
            i for i in instances
            if s in i.name.lower() or (getattr(i, "hasName", None) and s in i.hasName.lower())
        ]
    total = len(instances)
    start = (page - 1) * limit
    page_items = instances[start : start + limit]
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_serialize_entity(i) for i in page_items],
    }


def get_entity(uri: str) -> dict:
    onto = _require_onto()
    ind = onto.search_one(iri=f"*#{uri}")
    if ind is None:
        raise ValueError(f"Entity '{uri}' not found")
    return _serialize_entity(ind, include_relationships=True)


def get_entity_graph(uri: str) -> dict:
    onto = _require_onto()
    ind = onto.search_one(iri=f"*#{uri}")
    if ind is None:
        raise ValueError(f"Entity '{uri}' not found")

    nodes, links = {}, []
    cls_name = type(ind).name if hasattr(type(ind), "name") else "Unknown"
    nodes[ind.name] = _graph_node(ind, cls_name)

    for prop in ind.get_properties():
        values = prop[ind]
        if not isinstance(values, list):
            values = [values] if values is not None else []
        for val in values:
            if hasattr(val, "name"):
                target_cls = type(val).name if hasattr(type(val), "name") else "Unknown"
                nodes[val.name] = _graph_node(val, target_cls)
                links.append({"source": ind.name, "target": val.name, "label": prop.python_name})

    for prop, source in ind.get_inverse_properties():
        if hasattr(source, "name"):
            src_cls = type(source).name if hasattr(type(source), "name") else "Unknown"
            nodes[source.name] = _graph_node(source, src_cls)
            links.append({"source": source.name, "target": ind.name, "label": prop.python_name})

    return {"nodes": list(nodes.values()), "links": links}


def get_full_graph(
    types: Union[List[str], None] = None,
    state_fips: Union[str, None] = None,
    limit: int = 500,
) -> dict:
    onto = _require_onto()
    types = types or ["State", "County", "Municipality", "Individual"]

    # Build county filter if a state is focused
    focus_state = None
    focus_counties = None
    if state_fips:
        focus_state = onto.search_one(iri=f"*#State_{state_fips}")
        if focus_state:
            county_cls = next((c for c in onto.classes() if c.name == "County"), None)
            if county_cls:
                focus_counties = {
                    ind for ind in county_cls.instances()
                    if _first(getattr(ind, "isPartOf", None)) == focus_state
                }

    nodes: dict[str, dict] = {}
    for cls_name in types:
        cls = next((c for c in onto.classes() if c.name == cls_name), None)
        if cls is None:
            continue
        for ind in cls.instances():
            if state_fips and focus_state:
                if cls_name == "County" and _first(getattr(ind, "isPartOf", None)) != focus_state:
                    continue
                if cls_name == "Municipality":
                    if focus_counties is None or _first(getattr(ind, "isPartOf", None)) not in focus_counties:
                        continue
            elif cls_name == "Municipality":
                continue  # too many without a state filter
            nodes[ind.name] = _graph_node(ind, cls_name)
            if len(nodes) >= limit:
                break
        if len(nodes) >= limit:
            break

    node_set = set(nodes.keys())
    links = []
    seen = set()
    for name, node_data in nodes.items():
        ind = onto.search_one(iri=f"*#{name}")
        if ind is None:
            continue
        for prop in ind.get_properties():
            values = prop[ind]
            if not isinstance(values, list):
                values = [values] if values is not None else []
            for val in values:
                if hasattr(val, "name") and val.name in node_set:
                    key = (name, val.name, prop.python_name)
                    if key not in seen:
                        seen.add(key)
                        links.append({"source": name, "target": val.name, "label": prop.python_name})

    return {"nodes": list(nodes.values()), "links": links}


def search_entities(q: str, types: Union[List[str], None] = None) -> List[dict]:
    onto = _require_onto()
    results = []
    q_lower = q.lower()
    for cls in onto.classes():
        if types and cls.name not in types:
            continue
        for ind in cls.instances():
            if q_lower in ind.name.lower() or (
                getattr(ind, "hasName", None) and q_lower in ind.hasName.lower()
            ):
                results.append(_serialize_entity(ind))
    return results[:100]


def list_series() -> list[str]:
    onto = _require_onto()
    measure_cls = next((c for c in onto.classes() if c.name == "Measure"), None)
    if not measure_cls:
        return []
    return sorted({
        getattr(m, "hasSeries", None)
        for m in measure_cls.instances()
        if getattr(m, "hasSeries", None)
    })


def list_search_documents() -> list[dict]:
    onto = _require_onto()
    documents = []
    for cls in onto.classes():
        for ind in cls.instances():
            entity = _serialize_entity(ind)
            documents.append(
                {
                    "entity": entity,
                    "text": _entity_search_text(entity),
                }
            )
    return documents


def _export_to_duckdb_sync(duckdb_path: str) -> None:
    """
    Export all OWL individuals to DuckDB tables.
    Each class becomes a table; data properties become columns.
    Must be called within the executor thread (uses _world directly).
    """
    import duckdb
    import pandas as pd

    onto = _require_onto()
    con = duckdb.connect(duckdb_path)
    try:
        for cls in onto.classes():
            rows = []
            for ind in list(cls.instances()):
                row: dict = {"_iri": ind.iri, "_id": ind.name}
                for prop in ind.get_properties():
                    try:
                        vals = prop[ind]
                        if not vals:
                            continue
                        val = vals[0] if isinstance(vals, list) else vals
                        # Skip object properties (they have an iri / storid)
                        if hasattr(val, "storid") or hasattr(val, "iri"):
                            continue
                        col = prop.python_name or prop.name
                        row[col] = val
                    except Exception:
                        pass
                rows.append(row)

            if rows:
                df = pd.DataFrame(rows)
                con.register("_tmp_df", df)
                con.execute(f'CREATE OR REPLACE TABLE "{cls.name}" AS SELECT * FROM _tmp_df')
                con.unregister("_tmp_df")
    finally:
        con.close()


async def export_to_duckdb(duckdb_path: str) -> None:
    """Async wrapper: export ontology to DuckDB. Runs in the ontology executor."""
    await _run(_export_to_duckdb_sync, duckdb_path)


def get_series_data(series_id: str) -> list[dict]:
    onto = _require_onto()
    measure_cls = next((c for c in onto.classes() if c.name == "Measure"), None)
    if not measure_cls:
        return []
    rows = [
        {"date": m.hasDate, "value": m.hasValue}
        for m in measure_cls.instances()
        if getattr(m, "hasSeries", None) == series_id
        and m.hasDate and m.hasValue is not None
    ]
    return sorted(rows, key=lambda r: r["date"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first(val):
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _serialize_entity(ind, include_relationships: bool = False) -> dict:
    cls_name = type(ind).name if hasattr(type(ind), "name") else "Unknown"
    result = {
        "id": ind.name,
        "iri": ind.iri,
        "class": cls_name,
        "properties": {},
    }
    for attr in ("hasName", "hasPopulation", "hasFIPS", "hasIncome",
                 "hasValue", "hasDate", "hasSeries", "hasUnit"):
        val = getattr(ind, attr, None)
        if val is not None:
            result["properties"][attr] = val

    if include_relationships:
        rels = []
        for prop in ind.get_properties():
            values = prop[ind]
            if not isinstance(values, list):
                values = [values] if values is not None else []
            for val in values:
                if hasattr(val, "name"):
                    rels.append({"property": prop.python_name, "targetId": val.name,
                                 "targetName": getattr(val, "hasName", None) or val.name})
        for prop, source in ind.get_inverse_properties():
            if hasattr(source, "name"):
                rels.append({"property": f"←{prop.python_name}", "targetId": source.name,
                             "targetName": getattr(source, "hasName", None) or source.name})
        result["relationships"] = rels

    return result


def _entity_search_text(entity: dict) -> str:
    pieces = [entity["class"], entity["id"]]
    name = entity["properties"].get("hasName")
    if name:
        pieces.append(str(name))
    for key, value in entity["properties"].items():
        if key == "hasName" or value in (None, ""):
            continue
        pieces.append(f"{key} {value}")
    return ". ".join(str(piece) for piece in pieces if piece)


def _graph_node(ind, cls_name: str) -> dict:
    return {
        "id": ind.name,
        "label": getattr(ind, "hasName", None) or ind.name,
        "group": cls_name,
        "properties": {
            attr: getattr(ind, attr)
            for attr in ("hasName", "hasPopulation", "hasFIPS", "hasValue", "hasDate", "hasSeries")
            if getattr(ind, attr, None) is not None
        },
    }
