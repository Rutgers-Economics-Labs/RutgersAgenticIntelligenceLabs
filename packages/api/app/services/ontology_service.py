"""
Project-aware OWL quadstore access (onto.db via Owlready2).

Historically this service used a single global in-memory ontology.
We now support per-project ontologies by keeping separate Owlready2 Worlds,
each guarded by its own single-thread executor (Owlready2 SQLite backend is not thread-safe).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Union, List

from owlready2 import World, ObjectProperty

GLOBAL_PROJECT_ID = "__global__"


@dataclass
class _ProjectOntology:
    project_id: str
    lock: Lock
    world: World | None = None
    onto: Any | None = None
    db_path: str | None = None
    executor: Any | None = None


_states_by_id: dict[str, _ProjectOntology] = {}
_states_by_path: dict[str, _ProjectOntology] = {}
_states_lock = Lock()


def _get_state(project_id: str | None, db_path: str | None = None) -> _ProjectOntology:
    pid = project_id or GLOBAL_PROJECT_ID
    
    with _states_lock:
        st = _states_by_id.get(pid)
        if st is not None:
            # Check if this PID's assigned path changed:
            if db_path and st.db_path and st.db_path != db_path:
                print(f"  [ontology_service] project={pid} path changed {st.db_path} -> {db_path}")
                # We need to re-link or re-initialize.
                pass
            return st
        
        # If no state for PID, check if we have one for the same path:
        if db_path:
            st = _states_by_path.get(db_path)
            if st:
                print(f"  [ontology_service] project={pid} sharing world for path {db_path}")
                _states_by_id[pid] = st
                return st
        
        # Initialize new state:
        st = _ProjectOntology(project_id=pid, lock=Lock())
        _states_by_id[pid] = st
        if db_path:
            _states_by_path[db_path] = st
        return st


def _get_executor(st: _ProjectOntology):
    import concurrent.futures

    if st.executor is None:
        st.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    return st.executor


def load(db_path: Union[str, Path], *, project_id: str | None = None) -> None:
    """Load (or reload) the quadstore for project_id from db_path. Thread-safe."""
    db_path = str(Path(db_path).resolve())
    st = _get_state(project_id, db_path)
    with st.lock:
        _load_locked(st, db_path)


def _load_locked(st: _ProjectOntology, db_path: str) -> None:
    """Load the quadstore with st.lock already held."""
    if st.world is not None:
        st.world.close()
    st.world = World()
    # Owlready2 uses SQLite; on some systems we can see transient "database is locked"
    # during concurrent access / background jobs. Retry briefly to avoid 500s.
    last_err: Exception | None = None
    for attempt in range(12):
        try:
            st.world.set_backend(filename=db_path, exclusive=False)
            last_err = None
            break
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "database is locked" not in msg and "locked" not in msg:
                raise
            # Back off and wait for lock release
            time.sleep(0.1 * (2**attempt if attempt < 5 else 32))
    if last_err is not None:
        raise last_err

    stored = list(st.world.ontologies.values())
    if not stored:
        raise RuntimeError(f"No ontology found in quadstore at {db_path}.")

    filtered = [o for o in stored if o.base_iri != "http://anonymous/"]
    st.onto = filtered[0] if filtered else stored[0]
    st.db_path = db_path
    print(
        f"  [load] project={st.project_id} ontology={st.onto.base_iri} ({len(list(st.onto.classes()))} classes found)"
    )


def ensure_loaded(db_path: Union[str, Path], *, project_id: str | None = None) -> None:
    db_path = str(Path(db_path).resolve())
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"Ontology artifact not found at {db_path}. "
            "The /tmp/ files may have been cleaned up — re-run hydration to regenerate them."
        )
    st = _get_state(project_id, db_path)
    
    # Update pathological mapping if we just discovered this PID uses this shared path:
    with _states_lock:
        if db_path not in _states_by_path:
            _states_by_path[db_path] = st
            
    # Guard the check + load together to prevent concurrent requests from both
    # trying to open/analyze the same SQLite quadstore at once.
    with st.lock:
        if st.db_path != db_path or st.onto is None or st.world is None:
            _load_locked(st, db_path)


def _require_onto(project_id: str | None = None):
    st = _get_state(project_id)
    if st.onto is None:
        raise RuntimeError("Ontology not loaded. Run a hydration job first.")
    return st.onto


def get_db_path(project_id: str | None = None) -> Union[str, None]:
    return _get_state(project_id).db_path


async def _run(project_id: str | None, fn, *args, **kwargs):
    """Run a sync ontology function within the project's dedicated thread executor."""
    st = _get_state(project_id)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_get_executor(st), lambda: fn(project_id, *args, **kwargs))


async def ensure_loaded_async(db_path: Union[str, Path], *, project_id: str | None = None) -> None:
    """
    Load the quadstore on the project's ontology thread.

    Call this instead of ensure_loaded() from asyncio routes: Owlready2's SQLite
    backend must be used from a single thread; ensure_loaded on the event-loop
    thread while _run() uses the executor caused deadlocks/hangs.
    """
    db_path = str(Path(db_path).resolve())
    st = _get_state(project_id, db_path)
    loop = asyncio.get_event_loop()

    def sync_work():
        ensure_loaded(db_path, project_id=project_id)

    await loop.run_in_executor(_get_executor(st), sync_work)


async def _run_with_ensure(
    project_id: str | None,
    db_path: str,
    fn,
    *args,
    **kwargs,
):
    """ensure_loaded + fn in one executor job (same thread, safe for Owlready2)."""
    st = _get_state(project_id, str(Path(db_path).resolve()))
    loop = asyncio.get_event_loop()

    def sync_work():
        ensure_loaded(db_path, project_id=project_id)
        return fn(project_id, *args, **kwargs)

    return await loop.run_in_executor(_get_executor(st), sync_work)


# ---------------------------------------------------------------------------
# Query functions (all sync; call via _run() from async endpoints)
# ---------------------------------------------------------------------------

def list_classes(project_id: str | None = None) -> list[dict]:
    onto = _require_onto(project_id)
    return sorted(
        [
            {"name": cls.name, "count": len(list(cls.instances()))}
            for cls in onto.classes()
        ],
        key=lambda c: c["name"],
    )


def list_instances(
    project_id: str | None,
    class_name: str,
    page: int = 1,
    limit: int = 50,
    search: str = "",
) -> dict:
    onto = _require_onto(project_id)
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


def get_entity(project_id: str | None, uri: str) -> dict:
    onto = _require_onto(project_id)
    ind = onto.search_one(iri=f"*#{uri}")
    if ind is None:
        raise ValueError(f"Entity '{uri}' not found")
    return _serialize_entity(ind, include_relationships=True)


def get_entity_graph(project_id: str | None, uri: str) -> dict:
    onto = _require_onto(project_id)
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
                    target_id = str(val.name)
                    nodes[target_id] = _graph_node(val, target_cls)
                    links.append({"source": str(ind.name), "target": target_id, "label": str(getattr(prop, "python_name", prop.name))})
        except Exception:
            continue

    for prop, source in ind.get_inverse_properties():
        if hasattr(source, "name"):
            src_cls = type(source).name if hasattr(type(source), "name") else "Unknown"
            src_id = str(source.name)
            nodes[src_id] = _graph_node(source, src_cls)
            links.append({"source": src_id, "target": str(ind.name), "label": str(getattr(prop, "python_name", prop.name))})

    return {"nodes": list(nodes.values()), "links": links}


def get_full_graph(
    project_id: str | None,
    types: Union[List[str], None] = None,
    state_fips: Union[str, None] = None,
    limit: int = 500,
) -> dict:
    onto = _require_onto(project_id)
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


def get_class_graph(project_id: str | None) -> dict:
    """Class-level ontology graph: entities as types, edges as object properties."""
    onto = _require_onto(project_id)
    class_names = {c.name for c in onto.classes()}
    nodes: list[dict] = []
    links: list[dict] = []
    seen_links: set[tuple[str, str, str]] = set()

    for cls in onto.classes():
        count = len(list(cls.instances()))
        nodes.append(
            {
                "id": cls.name,
                "label": cls.name,
                "group": cls.name,
                "count": count,
                "properties": {"instances": count},
            }
        )

    for prop in onto.object_properties():
        try:
            domains = list(prop.domain) if prop.domain else []
            ranges = list(prop.range) if prop.range else []
        except Exception:
            continue
        label = str(getattr(prop, "python_name", None) or getattr(prop, "name", "relates"))
        for domain in domains:
            d_name = getattr(domain, "name", None)
            if not d_name or d_name not in class_names:
                continue
            for range_cls in ranges:
                r_name = getattr(range_cls, "name", None)
                if not r_name or r_name not in class_names:
                    continue
                key = (d_name, r_name, label)
                if key in seen_links:
                    continue
                seen_links.add(key)
                links.append({"source": d_name, "target": r_name, "label": label})

    # Fallback: link Observation to classes that share time-series columns in DuckDB mirror
    if "Observation" in class_names and not links:
        for cls_name in class_names:
            if cls_name != "Observation":
                links.append({"source": cls_name, "target": "Observation", "label": "observedAs"})

    return {"nodes": nodes, "links": links}


def get_database_graph(project_id: str | None, db_path: str | None = None) -> dict:
    """Table-level graph of the hydrated DuckDB artifact (row counts + shared columns)."""
    import duckdb

    path = db_path or get_db_path(project_id)
    if not path:
        raise RuntimeError("Database path unavailable. Run hydration first.")
    path = str(Path(path).resolve())
    if path.endswith(".db") and not path.endswith(".duckdb"):
        duck = path.replace(".db", ".duckdb")
        if Path(duck).exists():
            path = duck

    if not Path(path).exists():
        raise FileNotFoundError(f"DuckDB artifact not found at {path}")

    con = duckdb.connect(path, read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        schema: dict[str, list[str]] = {}
        nodes: list[dict] = []
        for table in sorted(tables):
            count = int(con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            cols = [r[0] for r in con.execute(f'DESCRIBE "{table}"').fetchall()]
            schema[table] = cols
            nodes.append(
                {
                    "id": table,
                    "label": table,
                    "group": "table",
                    "count": count,
                    "properties": {"rows": count, "columns": cols},
                }
            )

        skip_cols = {"_id", "_iri", "id", "row_is_current"}
        links: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        table_set = set(tables)
        for t1, cols1 in schema.items():
            for t2, cols2 in schema.items():
                if t1 >= t2:
                    continue
                shared = set(cols1) & set(cols2) - skip_cols
                for col in sorted(shared):
                    if col.startswith("_"):
                        continue
                    key = (t1, t2, col)
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append({"source": t1, "target": t2, "label": col})
                # Heuristic: column name matches another table (e.g. municipality → Municipality)
                for col in cols1:
                    if col in skip_cols or not col[0].islower():
                        continue
                    candidate = col[0].upper() + col[1:]
                    if candidate in table_set and candidate != t1:
                        key = (t1, candidate, col)
                        if key not in seen:
                            seen.add(key)
                            links.append({"source": t1, "target": candidate, "label": col})

        return {"nodes": nodes, "links": links}
    finally:
        con.close()


def search_entities(project_id: str | None, q: str, types: Union[List[str], None] = None) -> List[dict]:
    onto = _require_onto(project_id)
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


def within_radius(project_id: str | None, lat: float, lon: float, radius_km: float, types: List[str] = None) -> List[dict]:
    """
    GIS Spatial Query: Find entities within a radius using the DuckDB spatial mirror.
    Note: Requires that the ontology has been exported to DuckDB and contains
    hasLatitude / hasLongitude properties.
    """
    import duckdb
    from app.services import config_service

    db_path = get_db_path(project_id)
    db_path = db_path.replace(".db", ".duckdb") if db_path else "ontology/onto.duckdb"
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


def update_entity_property(project_id: str | None, uri: str, prop_name: str, value: Any):
    """
    Streaming/Real-time Update: Modifies a single triple in the SQLite quadstore.
    Thread-safe and atomic.
    """
    st = _get_state(project_id)
    onto = _require_onto(project_id)
    ind = onto.search_one(iri=f"*#{uri}")
    if ind is None:
        raise ValueError(f"Entity '{uri}' not found for update")

    prop = onto.search_one(python_name=prop_name)
    if prop is None:
        raise ValueError(f"Property '{prop_name}' not found")

    with st.lock:
        # Update owlready2 instance
        setattr(ind, prop_name, value)
        # Quadstore backend is updated immediately if it's already in a 'with onto:' context
        # but here we ensure it persists.
        st.world.save()

    print(f"[stream] Updated {uri}.{prop_name} = {value}")



def list_series(project_id: str | None = None) -> list[str]:
    """Return all distinct hasSeries values across any class that carries the property."""
    onto = _require_onto(project_id)
    series: set[str] = set()
    for cls in onto.classes():
        for ind in cls.instances():
            val = getattr(ind, "hasSeries", None)
            if val:
                series.add(val)
    return sorted(series)


def list_search_documents(project_id: str | None = None) -> list[dict]:
    onto = _require_onto(project_id)
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


def _export_to_duckdb_sync(project_id: str | None, duckdb_path: str) -> None:
    """
    Export all OWL individuals to DuckDB tables.
    Each class becomes a table; data properties become columns.
    Must be called within the executor thread (uses _world directly).
    """
    import duckdb
    import pandas as pd

    onto = _require_onto(project_id)
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


async def export_to_duckdb(project_id: str | None, duckdb_path: str) -> None:
    """Async wrapper: export ontology to DuckDB. Runs in the ontology executor."""
    await _run(project_id, _export_to_duckdb_sync, duckdb_path)


def get_series_data(project_id: str | None, series_id: str) -> list[dict]:
    """Return time-series rows for series_id from any class that carries hasSeries."""
    onto = _require_onto(project_id)
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
    import time
    # start = time.time()
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
            # Skip object properties (links) in the properties dict
            if hasattr(val, "iri"):
                continue
            
            pname = getattr(prop, "python_name", prop.name)
            # Ensure val is a primitive for JSON safety
            if hasattr(val, "__str__") and not isinstance(val, (str, int, float, bool)):
                val = str(val)
            result["properties"][pname] = val
        except Exception:
            pass

    # Explicitly include GIS fields if present for frontend mapping
    for gis_field in ["hasLatitude", "hasLongitude", "hasGeometry"]:
        try:
            val = getattr(ind, gis_field, None)
            if isinstance(val, list):
                val = val[0] if val else None
            if val is not None:
                if not isinstance(val, (str, int, float, bool)):
                    val = str(val)
                result["properties"][gis_field] = val
        except Exception:
            pass

    if include_relationships:
        rels = []
        # Forward relationships
        for prop in safe_props:
            try:
                values = prop[ind]
                if not isinstance(values, list):
                    values = [values] if values is not None else []
                for val in values:
                    if hasattr(val, "name"):
                        pname = getattr(prop, "python_name", prop.name)
                        rels.append({
                            "property": pname, 
                            "targetId": str(val.name),
                            "targetName": str(getattr(val, "hasName", None) or val.name)
                        })
            except Exception:
                pass
        
        # Inverse relationships — this can be slow, we'll wrap it in a try and keep it light
        try:
            # Only do this if it's a detail fetch, not a bulk list
            for prop, source in ind.get_inverse_properties():
                if hasattr(source, "name"):
                    pname = getattr(prop, "python_name", prop.name)
                    sid = str(getattr(source, "name", source))
                    sname = str(getattr(source, "hasName", None) or sid)
                    rels.append({
                        "property": f"←{pname}", 
                        "targetId": sid,
                        "targetName": sname
                    })
        except Exception:
            pass
        result["relationships"] = rels

    # print(f"  [_serialize_entity] {ind.name} took {time.time() - start:.4f}s")
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
            if not isinstance(val, (str, int, float, bool)):
                val = str(val)
            props[pname] = val
        except Exception:
            pass
    node_id = str(getattr(ind, "name", ind))
    return {
        "id": node_id,
        "label": str(props.get("hasName") or node_id),
        "group": str(cls_name),
        "properties": props,
    }
