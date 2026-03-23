"""
Minimal analysis plugin for smoke-testing the ontology pipeline.

Run via the API: POST /api/v1/analysis/plugins/example_basic_analysis/run
with body { "config": {} }.

Returns a short metrics block, a table of classes with instance counts,
and a text summary. Safe on empty or sparse graphs.
"""
import pandas as pd

NAME = "Example Basic Analysis (Smoke Test)"


def analyze(onto, **kwargs):
    classes = list(onto.classes())
    rows = []
    for cls in sorted(classes, key=lambda c: c.name):
        n = len(list(cls.instances()))
        if n:
            rows.append({"Class": cls.name, "Instances": n})

    total_instances = sum(r["Instances"] for r in rows)
    class_with_instances = len(rows)

    metric_items = [
        {"label": "OWL classes (total)", "value": len(classes)},
        {"label": "Classes with instances", "value": class_with_instances},
        {"label": "Total individuals", "value": total_instances},
    ]
    try:
        base_iri = str(onto.base_iri)
        if base_iri:
            metric_items.insert(0, {"label": "Ontology base IRI", "value": base_iri})
    except Exception:
        pass

    sections = [
        {"type": "metrics", "items": metric_items},
    ]

    if rows:
        df = (
            pd.DataFrame(rows)
            .sort_values("Instances", ascending=False)
            .reset_index(drop=True)
        )
        preview = df.head(25)
        sections.append({
            "type": "table",
            "title": "Classes with instances (top 25)",
            "data": preview,
        })
    else:
        sections.append({
            "type": "text",
            "content": "No individuals found on any class. Run a hydration pipeline first.",
        })

    sections.append({
        "type": "text",
        "content": (
            "**Smoke test OK.** This plugin only counts classes and instances. "
            "For deeper checks (properties, relationships), use the built-in "
            "`builtins` analysis or add your own logic here."
        ),
    })

    return {"title": NAME, "sections": sections}
