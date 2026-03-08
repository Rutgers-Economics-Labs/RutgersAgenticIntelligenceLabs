"""
Built-in ontology analysis.
Runs four standard analyses on any ontology loaded by RAIL:
  1. Entity Summary      — count of each type
  2. Property Completeness — % filled per class×property
  3. Population Insights  — top/bottom states and counties by population
  4. Relationship Coverage — % of entities with each object property linked
"""
import pandas as pd
from owlready2 import ObjectProperty

NAME = "Built-in Ontology Analysis"


def analyze(onto, **kwargs):
    sections = []

    sections.append(_entity_summary(onto))
    sections.append({"type": "divider"})
    sections.append(_property_completeness(onto))
    sections.append({"type": "divider"})
    sections.extend(_population_insights(onto))
    sections.append({"type": "divider"})
    sections.append(_relationship_coverage(onto))

    return {"title": NAME, "sections": sections}


# ---------------------------------------------------------------------------

def _entity_summary(onto):
    rows = [
        {"Type": cls.name, "Instances": len(list(cls.instances()))}
        for cls in sorted(onto.classes(), key=lambda c: c.name)
        if list(cls.instances())
    ]
    total = sum(r["Instances"] for r in rows)
    rows.append({"Type": "TOTAL", "Instances": total})
    return {
        "type": "table",
        "title": "Entity Summary",
        "data": pd.DataFrame(rows),
    }


def _property_completeness(onto):
    rows = []
    for cls in sorted(onto.classes(), key=lambda c: c.name):
        instances = list(cls.instances())
        if not instances:
            continue
        for prop in sorted(onto.properties(), key=lambda p: p.python_name):
            vals = [getattr(ind, prop.python_name, None) for ind in instances]
            filled = sum(
                1 for v in vals
                if v is not None and v != [] and v != ""
            )
            if filled == 0:
                continue
            rows.append({
                "Class":        cls.name,
                "Property":     prop.python_name,
                "Filled":       filled,
                "Total":        len(instances),
                "Completeness": f"{filled / len(instances) * 100:.1f}%",
            })
    return {
        "type": "table",
        "title": "Property Completeness",
        "data": pd.DataFrame(rows) if rows else pd.DataFrame(),
    }


def _population_insights(onto):
    sections = []

    for cls_name, n in [("State", 10), ("County", 10)]:
        cls = next((c for c in onto.classes() if c.name == cls_name), None)
        if cls is None:
            continue
        rows = [
            {"Name": getattr(ind, "hasName", ind.name),
             "Population": getattr(ind, "hasPopulation", None)}
            for ind in cls.instances()
        ]
        rows = [r for r in rows if r["Population"] is not None]
        if not rows:
            continue
        df = pd.DataFrame(rows).sort_values("Population", ascending=False)
        df["Population"] = df["Population"].apply(lambda x: f"{x:,}")
        sections.append({
            "type": "table",
            "title": f"Top {n} {cls_name}s by Population",
            "data": df.head(n).reset_index(drop=True),
        })

    return sections


def _relationship_coverage(onto):
    rows = []
    obj_props = [p for p in onto.properties() if issubclass(p, ObjectProperty)]
    for prop in sorted(obj_props, key=lambda p: p.python_name):
        domain = prop.domain or []
        for cls in domain:
            instances = list(cls.instances())
            if not instances:
                continue
            linked = sum(
                1 for ind in instances
                if getattr(ind, prop.python_name, None) not in (None, [])
            )
            rows.append({
                "Class":    cls.name,
                "Property": prop.python_name,
                "Linked":   linked,
                "Total":    len(instances),
                "Coverage": f"{linked / len(instances) * 100:.1f}%",
            })
    return {
        "type": "table",
        "title": "Relationship Coverage",
        "data": pd.DataFrame(rows) if rows else pd.DataFrame(),
    }
