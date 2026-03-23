"""
Temporary owlready2 inspector for the hydrated RAIL ontology.

Run from packages/engine (default paths):
  python temp_inspect_ontology.py

Or:
  python temp_inspect_ontology.py --db path/to/onto.db

Requires: owlready2 (same as hydrate). Safe to delete when no longer needed.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from owlready2 import World

# Must match configs/ontology/core.yaml `uri`
DEFAULT_ONTO_IRI = "http://example.org/rutgers_ontology.owl"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a summary of the RAIL ontology quadstore.")
    parser.add_argument(
        "--db",
        default=os.environ.get("RAIL_ONTO_DB", "ontology/onto.db"),
        help="Path to onto.db (default: ontology/onto.db or RAIL_ONTO_DB)",
    )
    parser.add_argument(
        "--iri",
        default=os.environ.get("RAIL_ONTO_IRI", DEFAULT_ONTO_IRI),
        help="Ontology IRI to load from the quadstore",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=2,
        help="Sample individuals per class (default: 2)",
    )
    args = parser.parse_args()

    db = Path(args.db)
    if not db.is_file():
        raise SystemExit(f"Missing database file: {db.resolve()}\nRun: python hydrate.py")

    world = World()
    world.set_backend(filename=str(db))
    onto = world.get_ontology(args.iri).load()

    print(f"Ontology IRI: {onto.base_iri}")
    print(f"Quadstore:    {db.resolve()}")
    print()

    # --- Classes with instance counts ---
    rows: list[tuple[str, int]] = []
    for cls in onto.classes():
        name = cls.name
        if name == "Thing":
            continue
        try:
            n = len(list(cls.instances()))
        except Exception:
            n = -1
        rows.append((name, n))
    rows.sort(key=lambda x: (-x[1], x[0]))

    print("Classes (by instance count, then name)")
    print("-" * 48)
    for name, n in rows:
        if n < 0:
            print(f"  {name}: (could not count)")
            continue
        if n == 0:
            continue
        print(f"  {name}: {n:,}")
    print("-" * 48)
    print(f"  (Rows above can double-count if instances have multiple types.)\n")

    # --- Sample individuals ---
    print(f"Samples (up to {args.samples} per class with instances)")
    print("-" * 48)
    for cls in sorted(onto.classes(), key=lambda c: c.name):
        if cls.name == "Thing":
            continue
        insts = list(cls.instances())
        if not insts:
            continue
        print(f"\n[{cls.name}]")
        for ind in insts[: args.samples]:
            label = getattr(ind, "hasName", None) or ind.name
            iri = ind.iri if hasattr(ind, "iri") else str(ind)
            line = f"  - {label!r}  ({iri})"
            # Common literals for this project
            bits = []
            for attr in ("hasFIPS", "hasPopulation", "hasSeries", "hasDate", "hasValue"):
                v = getattr(ind, attr, None)
                if v is not None and v != []:
                    bits.append(f"{attr}={v!r}")
            if bits:
                line += "\n    " + ", ".join(bits)
            print(line)

    # --- Properties (declared on this ontology) ---
    print("\n\nData properties")
    print("-" * 48)
    for p in sorted(onto.data_properties(), key=lambda x: x.name):
        if p.name == "topDataProperty":
            continue
        print(f"  {p.name}")

    print("\nObject properties")
    print("-" * 48)
    for p in sorted(onto.object_properties(), key=lambda x: x.name):
        if p.name == "topObjectProperty":
            continue
        print(f"  {p.name}")

    if hasattr(world, "graph") and hasattr(world.graph, "db"):
        world.graph.db.close()


if __name__ == "__main__":
    main()
