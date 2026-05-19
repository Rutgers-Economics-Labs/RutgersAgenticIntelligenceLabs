#!/usr/bin/env python3
"""Compute headline NJ housing summary stats from the populated DuckDB ontology.

Reproducible verification command for the `coding` worker phase.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

DB_PATH = Path(".ontology/onto.duckdb")
OUTPUT = Path(".ontology/derived/nj_housing_summary_stats.json")


def _pct(series):
    return (series[-1] - series[0]) / series[0] * 100.0 if series else 0.0


def main() -> int:
    if not DB_PATH.exists():
        print(f"DuckDB not found: {DB_PATH}", file=sys.stderr)
        return 1
    db = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        hpi = [row[1] for row in db.execute("SELECT date, value FROM housing_price_index ORDER BY date").fetchall()]
        cpi = [row[1] for row in db.execute("SELECT date, value FROM cpi ORDER BY date").fetchall()]
        unemp = [row[1] for row in db.execute("SELECT date, value FROM unemployment_rate ORDER BY date").fetchall()]
    finally:
        db.close()
    payload = {
        "hpiPctChange": round(_pct(hpi), 2),
        "cpiPctChange": round(_pct(cpi), 2),
        "unempStart": round(unemp[0], 2) if unemp else None,
        "unempEnd": round(unemp[-1], 2) if unemp else None,
        "realAffordabilityChange": round(_pct(hpi) - _pct(cpi), 2),
        "hpiObservations": len(hpi),
        "unempObservations": len(unemp),
        "cpiObservations": len(cpi),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
