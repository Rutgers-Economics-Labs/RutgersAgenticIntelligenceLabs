"""
Example custom analysis: NJ Unemployment Trends.

Drop your own .py files in analysis/ — any file with analyze(onto) gets
picked up automatically in the Analysis tab.

analyze() receives the full owlready2 ontology and returns a result dict.
See analysis/builtins.py for the full section type reference.
"""
import pandas as pd

NAME = "NJ Unemployment Trends"


def analyze(onto, **kwargs):
    measure_class = next((c for c in onto.classes() if c.name == "Measure"), None)
    if measure_class is None:
        return {"title": NAME, "sections": [
            {"type": "text", "content": "No `Measure` class found in ontology."}
        ]}

    unemp = [
        {"date": m.hasDate, "value": m.hasValue}
        for m in measure_class.instances()
        if getattr(m, "hasSeries", None) == "NJURN"
        and m.hasDate and m.hasValue is not None
    ]
    if not unemp:
        return {"title": NAME, "sections": [
            {"type": "text", "content": "No NJURN data found. Run hydrate.py with FRED steps."}
        ]}

    df = pd.DataFrame(unemp).sort_values("date").reset_index(drop=True)
    latest = df.iloc[-1]
    peak   = df.loc[df["value"].idxmax()]
    trough = df.loc[df["value"].idxmin()]
    mean   = df["value"].mean()

    # Year-over-year change (last 12 monthly observations)
    yoy_delta = None
    if len(df) >= 13:
        yoy_delta = df.iloc[-1]["value"] - df.iloc[-13]["value"]

    metric_items = [
        {"label": "Latest",         "value": f"{latest['value']:.1f}%  ({latest['date']})"},
        {"label": "Historical Mean","value": f"{mean:.2f}%"},
        {"label": "Peak",           "value": f"{peak['value']:.1f}%  ({peak['date']})"},
        {"label": "Trough",         "value": f"{trough['value']:.1f}%  ({trough['date']})"},
    ]
    if yoy_delta is not None:
        metric_items.append({"label": "YoY Change", "value": f"{yoy_delta:+.1f} pp"})

    return {
        "title": NAME,
        "sections": [
            {"type": "metrics", "items": metric_items},
            {"type": "chart",
             "title": "NJ Unemployment Rate (Monthly, %)",
             "data": df, "x": "date", "y": "value"},
            {"type": "text", "content": (
                "**Source:** Bureau of Labor Statistics — LAUS programme via FRED (`NJURN`).  \n"
                "Values are seasonally adjusted monthly unemployment rates."
            )},
        ],
    }
