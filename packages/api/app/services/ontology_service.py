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
        # Discover which ontology is stored in this quadstore dynamically.
        # This works for any YAML-defined schema — no hardcoded IRI required.
        # owlready2 populates _world.ontologies after set_backend() when the DB
        # already has triples; we just grab the first (and usually only) one.
        stored = list(_world.ontologies.values())
        if not stored:
             raise RuntimeError(f"No ontology found in quadstore at {db_path}.")

        # Prefer the first one that isn't 'http://anonymous/'
        filtered = [o for o in stored if o.base_iri != "http://anonymous/"]
        if filtered:
            _onto = filtered[0]
        else:
            _onto = stored[0]

        print(f"  [load] Active ontology: {_onto.base_iri} ({len(list(_onto.classes()))} classes found)")
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

    safe_props = ind.get_properties() if hasattr(ind, "get_properties") else []
    for prop in safe_props:
        try:
            values = prop[ind]
            if not isinstance(values, list):
                values = [values] if values is not None else []
            for val in values:
                if hasattr(val, "name"):
                    target_cls = type(val).name if hasattr(type(val), "name") else "Unknown"
                    nodes[val.name] = _graph_node(val, target_cls)
                    links.append({"source": ind.name, "target": val.name, "label": getattr(prop, "python_name", prop.name)})
        except Exception:
            continue

    for prop, source in ind.get_inverse_properties():
        if hasattr(source, "name"):
            src_cls = type(source).name if hasattr(type(source), "name") else "Unknown"
            nodes[source.name] = _graph_node(source, src_cls)
            links.append({"source": source.name, "target": ind.name, "label": getattr(prop, "python_name", prop.name)})

    return {"nodes": list(nodes.values()), "links": links}


def get_full_graph(
    types: Union[List[str], None] = None,
    state_fips: Union[str, None] = None,
    limit: int = 500,
) -> dict:
    onto = _require_onto()
    all_class_names = [c.name for c in onto.classes()]
    # Default to all classes in the ontology — generalized for any schema
    types = types or all_class_names

    # When a state_fips filter is given, try to narrow via isPartOf if it exists
    # (works even if class is not named "County" — any class with isPartOf linking to a State_* uri)
    focus_state = None
    if state_fips:
        focus_state = onto.search_one(iri=f"*#State_{state_fips}")

    nodes: dict[str, dict] = {}
    for cls_name in types:
        cls = next((c for c in onto.classes() if c.name == cls_name), None)
        if cls is None:
            continue
        instance_count = 0
        for ind in cls.instances():
            if focus_state:
                # Filter: skip if the individual is not connected to the focused state
                part_of = _first(getattr(ind, "isPartOf", None))
                located_in = _first(getattr(ind, "locatedIn", None))
                connected_state = part_of or located_in
                if connected_state is not None and connected_state != focus_state:
                    # Also accept children of focus_state (e.g. Municipality inside County inside State)
                    grandparent = _first(getattr(connected_state, "isPartOf", None))
                    if grandparent != focus_state:
                        continue
            nodes[ind.name] = _graph_node(ind, cls_name)
            instance_count += 1
            if len(nodes) >= limit:
                break
        if len(nodes) >= limit:
            break

    node_set = set(nodes.keys())
    links = []
    seen = set()
    for name in node_set:
        ind = onto.search_one(iri=f"*#{name}")
        if ind is None:
            continue
        safe_props = ind.get_properties() if hasattr(ind, "get_properties") else []
        for prop in safe_props:
            try:
                values = prop[ind]
                if not isinstance(values, list):
                    values = [values] if values is not None else []
                for val in values:
                    if hasattr(val, "name") and val.name in node_set:
                        pname = getattr(prop, "python_name", prop.name)
                        key = (name, val.name, pname)
                        if key not in seen:
                            seen.add(key)
                            links.append({"source": name, "target": val.name, "label": pname})
            except Exception:
                pass

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


def within_radius(lat: float, lon: float, radius_km: float, types: List[str] = None) -> List[dict]:
    """
    GIS Spatial Query: Find entities within a radius using the DuckDB spatial mirror.
    Note: Requires that the ontology has been exported to DuckDB and contains
    hasLatitude / hasLongitude properties.
    """
    import duckdb
    from app.services import config_service

    db_path = _db_path.replace(".db", ".duckdb") if _db_path else "ontology/onto.duckdb"
    if not Path(db_path).exists():
        raise RuntimeError("GIS query requires DuckDB export. Run hydration first.")

    con = duckdb.connect(db_path)
    try:
        # Load spatial extension
        con.execute("INSTALL spatial; LOAD spatial;")

        # Search across all requested tables (classes)
        results = []
        types = types or ["GeographicRegion", "State", "County", "Municipality"]

        for table in types:
            try:
                # Use Haversine distance via DuckDB spatial for efficiency
                query = f"""
                    SELECT *,
                    st_distance_spheroid(st_point(hasLongitude, hasLatitude), st_point({lon}, {lat})) / 1000 as dist_km
                    FROM "{table}"
                    WHERE hasLatitude IS NOT NULL AND hasLongitude IS NOT NULL
                    AND dist_km <= {radius_km}
                    ORDER BY dist_km ASC
                    LIMIT 100
                """
                df = con.execute(query).df()
                for _, row in df.iterrows():
                    results.append({
                        "id": row["_id"],
                        "class": table,
                        "distance_km": row["dist_km"],
                        "properties": row.to_dict()
                    })
            except Exception:
                continue # Table might not exist yet

        return sorted(results, key=lambda x: x["distance_km"])
    finally:
        con.close()


def update_entity_property(uri: str, prop_name: str, value: Any):
    """
    Streaming/Real-time Update: Modifies a single triple in the SQLite quadstore.
    Thread-safe and atomic.
    """
    onto = _require_onto()
    ind = onto.search_one(iri=f"*#{uri}")
    if ind is None:
        raise ValueError(f"Entity '{uri}' not found for update")

    prop = onto.search_one(python_name=prop_name)
    if prop is None:
        raise ValueError(f"Property '{prop_name}' not found")

    with _lock:
        # Update owlready2 instance
        setattr(ind, prop_name, value)
        # Quadstore backend is updated immediately if it's already in a 'with onto:' context
        # but here we ensure it persists.
        _world.save()

    print(f"[stream] Updated {uri}.{prop_name} = {value}")



def list_series() -> list[str]:
    """Return all distinct hasSeries values across any class that carries the property."""
    onto = _require_onto()
    series: set[str] = set()
    for cls in onto.classes():
        for ind in cls.instances():
            val = getattr(ind, "hasSeries", None)
            if val:
                series.add(val)
    return sorted(series)


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
    """Return time-series rows for series_id from any class that carries hasSeries."""
    onto = _require_onto()
    rows = []
    for cls in onto.classes():
        for ind in cls.instances():
            if getattr(ind, "hasSeries", None) != series_id:
                continue
            date = getattr(ind, "hasDate", None)
            value = getattr(ind, "hasValue", None)
            if date and value is not None:
                rows.append({"date": date, "value": value})
    return sorted(rows, key=lambda r: r["date"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first(val):
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _serialize_entity(ind, include_relationships: bool = False) -> dict:
    """Serialize an individual dynamically — works for any class/property schema."""
    cls_name = type(ind).name if hasattr(type(ind), "name") else "Unknown"
    result = {
        "id": ind.name,
        "iri": ind.iri,
        "class": cls_name,
        "properties": {},
    }
    # Reflect all data properties
    safe_props = ind.get_properties() if hasattr(ind, "get_properties") else []
    for prop in safe_props:
        try:
            val = prop[ind]
            if isinstance(val, list):
                val = val[0] if val else None
            if val is None:
                continue
            if hasattr(val, "iri"):
                continue
            pname = getattr(prop, "python_name", prop.name)
            result["properties"][pname] = val
        except Exception:
            pass

    # Explicitly include GIS fields if present for frontend mapping
    for gis_field in ["hasLatitude", "hasLongitude", "hasGeometry"]:
        val = getattr(ind, gis_field, None)
        if val is not None:
             result["properties"][gis_field] = val


    if include_relationships:
        rels = []
        for prop in safe_props:
            try:
                values = prop[ind]
                if not isinstance(values, list):
                    values = [values] if values is not None else []
                for val in values:
                    if hasattr(val, "name"):
                        pname = getattr(prop, "python_name", prop.name)
                        rels.append({"property": pname, "targetId": val.name,
                                     "targetName": getattr(val, "hasName", None) or val.name})
            except Exception:
                pass
        for prop, source in ind.get_inverse_properties():
            if hasattr(source, "name"):
                pname = getattr(prop, "python_name", prop.name)
                sid = getattr(source, "name", str(source))
                rels.append({"property": f"←{pname}", "targetId": sid,
                             "targetName": getattr(source, "hasName", None) or sid})
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
    """Build a graph node, reflecting all data properties dynamically."""
    props: dict = {}
    safe_props = ind.get_properties() if hasattr(ind, "get_properties") else []
    for prop in safe_props:
        try:
            val = prop[ind]
            if isinstance(val, list):
                val = val[0] if val else None
            if val is None or hasattr(val, "iri"):
                continue
            pname = getattr(prop, "python_name", prop.name)
            props[pname] = val
        except Exception:
            pass
    return {
        "id": getattr(ind, "name", str(ind)),
        # Prefer hasName if present; otherwise fall back to the URI local name
        "label": props.get("hasName") or getattr(ind, "name", str(ind)),
        "group": cls_name,
        "properties": props,
    }
