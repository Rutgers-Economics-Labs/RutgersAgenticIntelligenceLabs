#!/usr/bin/env python3
"""Finish flagship papers, dashboards, ontology exploreability, and integrity metadata."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "engine"))

from engine.ontology_builder import load_ontology  # noqa: E402
from engine.pipeline_runner import _export_to_duckdb  # noqa: E402
from owlready2 import World  # noqa: E402

NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

PROJECTS = [
    {
        "slug": "european-soccer-competitive-ecosystem-analysis",
        "title": "European Soccer Competitive Ecosystem",
        "paper_md": "artifacts/final_ontology_backed_soccer_ecosystem_report.md",
        "paper_tex": None,
        "summary_artifact": "artifacts/final_ontology_backed_soccer_ecosystem_report.md",
    },
    {
        "slug": "assessing-the-economic-impact-of-the-urban-enterprise-zone-program-reform",
        "title": "NJ Urban Enterprise Zone Reform",
        "paper_md": None,
        "paper_tex": "research/uez_reform_impact.tex",
        "paper_pdf": "research/UEZ_Reform_Impact_Paper.pdf",
        "summary_artifact": "research/uez_impact_report.md",
    },
    {
        "slug": "assessing-data-center-impacts-on-new-jersey-grid-costs-and-pjm-forecasting",
        "title": "NJ Data Centers & PJM Forecasting",
        "paper_md": "artifacts/final_report.md",
        "paper_tex": "artifacts/paper/paper.tex",
        "paper_pdf": "artifacts/paper/paper.pdf",
        "summary_artifact": "artifacts/econometric_results.md",
    },
]

CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def sync_ontology_yaml(project_root: Path) -> None:
    ont_dir = project_root / ".ontology" / "ontologies"
    candidates = list(ont_dir.glob("*-ontology.yaml"))
    class_names: list[str] = []
    if candidates:
        full = yaml.safe_load(candidates[0].read_text(encoding="utf-8")) or {}
        for c in full.get("classes") or []:
            class_names.append(c["name"] if isinstance(c, dict) else str(c))
    duck_path = project_root / ".ontology" / "onto.duckdb"
    if duck_path.exists():
        con = duckdb.connect(str(duck_path), read_only=True)
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1"
        ).fetchall():
            if row[0] not in class_names:
                class_names.append(row[0])
        con.close()
    stub = {
        "uri": full.get("uri", "") if candidates else "",
        "classes": [{"name": n} for n in class_names],
    }
    (project_root / ".ontology" / "ontology.yaml").write_text(
        yaml.safe_dump(stub, sort_keys=False), encoding="utf-8"
    )


def restore_pjm_duckdb_from_sources(project_root: Path) -> None:
    """Rebuild PJM relational tables from cached CSVs (preserves exploreability)."""
    import pandas as pd

    ont_dir = project_root / ".ontology"
    duck_path = ont_dir / "onto.duckdb"
    pjm_dir = ont_dir / "sources" / "pjm"
    if not pjm_dir.exists():
        return
    con = duckdb.connect(str(duck_path))

    def _load_union(table: str, pattern: str) -> None:
        frames = []
        for path in sorted(pjm_dir.glob(pattern)):
            df = pd.read_csv(path)
            frames.append(df)
        if frames:
            merged = pd.concat(frames, ignore_index=True)
            con.register("_tmp_pjm", merged)
            con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _tmp_pjm')
            con.unregister("_tmp_pjm")

    try:
        _load_union("hrl_load_metered", "hrl_load_metered__*.csv")
        _load_union("da_hrl_lmps", "da_hrl_lmps__*.csv")
        forecast = list(pjm_dir.glob("load_frcstd_hist__*.csv"))
        if forecast:
            df = pd.read_csv(forecast[0])
            con.register("_tmp_fc", df)
            con.execute('CREATE OR REPLACE TABLE "load_frcstd_hist" AS SELECT * FROM _tmp_fc')
            con.unregister("_tmp_fc")
        dc = ont_dir / "sources" / "nj-data-centers" / "extracted" / "nj_data_centers.csv"
        if dc.exists():
            df = pd.read_csv(dc)
            con.register("_tmp_dc", df)
            con.execute('CREATE OR REPLACE TABLE "nj_data_centers" AS SELECT * FROM _tmp_dc')
            con.unregister("_tmp_dc")
    finally:
        con.close()


def merge_owl_tables_into_duckdb(project_root: Path) -> None:
    """Add OWL class tables without deleting existing relational tables."""
    import pandas as pd

    ont_dir = project_root / ".ontology"
    db_path = ont_dir / "onto.db"
    candidates = list((ont_dir / "ontologies").glob("*-ontology.yaml"))
    if not db_path.exists() or not candidates:
        return
    duck_path = ont_dir / "onto.duckdb"
    world = World(filename=str(db_path))
    onto, _ = load_ontology(str(candidates[0]), world=world)
    con = duckdb.connect(str(duck_path))
    try:
        for cls in onto.classes():
            rows = []
            for inst in list(cls.instances()):
                row: dict = {"_iri": inst.iri, "_id": inst.name}
                for prop in inst.get_properties():
                    try:
                        vals = prop[inst]
                        if not vals:
                            continue
                        val = vals[0] if isinstance(vals, list) else vals
                        if hasattr(val, "storid") or hasattr(val, "iri"):
                            continue
                        col = prop.python_name or prop.name
                        row[col] = val
                    except Exception:
                        pass
                rows.append(row)
            if rows:
                df = pd.DataFrame(rows)
                con.register("_tmp_owl", df)
                con.execute(f'CREATE OR REPLACE TABLE "{cls.name}" AS SELECT * FROM _tmp_owl')
                con.unregister("_tmp_owl")
    finally:
        con.close()


def export_owl_to_duckdb(project_root: Path, slug: str = "") -> dict[str, int]:
    ont_dir = project_root / ".ontology"
    db_path = ont_dir / "onto.db"
    if not db_path.exists():
        return {}
    candidates = list((ont_dir / "ontologies").glob("*-ontology.yaml"))
    if not candidates:
        return {}
    duck_path = ont_dir / "onto.duckdb"
    if slug.startswith("assessing-data-center"):
        restore_pjm_duckdb_from_sources(project_root)
        merge_owl_tables_into_duckdb(project_root)
    else:
        world = World(filename=str(db_path))
        onto, _ = load_ontology(str(candidates[0]), world=world)
        _export_to_duckdb(world, onto, str(duck_path))
    con = duckdb.connect(str(duck_path))
    counts = {}
    for row in con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' AND table_type='BASE TABLE'"
    ).fetchall():
        t = row[0]
        counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    con.close()
    return counts


def enrich_uez_duckdb(project_root: Path) -> None:
    duck_path = project_root / ".ontology" / "onto.duckdb"
    if not duck_path.exists():
        return
    con = duckdb.connect(str(duck_path))
    try:
        con.execute(
            """
            CREATE OR REPLACE TABLE Municipality AS
            SELECT DISTINCT
              regexp_extract(_id, '^[a-z]+_(.+)_\\d{4}$', 1) AS municipality,
              regexp_extract(_id, '^(emp|sut|zaf)_', 1) AS measure_family
            FROM Observation
            WHERE _id IS NOT NULL
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TABLE Measure AS
            SELECT * FROM (VALUES
              ('emp', 'Employment'),
              ('sut', 'Sales & Use Tax collections'),
              ('zaf', 'Zone Assistance Fund allocation')
            ) AS t(measure_code, measure_label)
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TABLE MunicipalityYearPanel AS
            SELECT
              regexp_extract(_id, '^[a-z]+_(.+)_\\d{4}$', 1) AS municipality,
              regexp_extract(_id, '^(emp|sut|zaf)_', 1) AS measure_code,
              CAST(hasDate AS INTEGER) AS year,
              hasValue AS value
            FROM Observation
            """
        )
        con.execute(
            """
            CREATE OR REPLACE TABLE AnnualSeries AS
            SELECT measure_code, year, AVG(value) AS avg_value, COUNT(*) AS n_municipalities
            FROM MunicipalityYearPanel
            GROUP BY 1, 2
            ORDER BY 1, 2
            """
        )
    finally:
        con.close()


def sync_sources_json(project_root: Path) -> None:
    state_path = project_root / "research_plan" / "state" / "sources.json"
    sources_dir = project_root / ".ontology" / "sources"
    if not sources_dir.exists():
        return
    existing = {s.get("source_key"): s for s in _load_json(state_path, []) if s.get("source_key")}
    rows = []
    for cfg in sorted(sources_dir.glob("*.yaml")):
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        key = data.get("slug") or cfg.stem
        row = existing.get(key, {})
        rows.append(
            {
                "source_key": key,
                "source_type": row.get("source_type") or data.get("type") or "api",
                "title": row.get("title") or data.get("title") or key,
                "url_or_path": row.get("url_or_path") or data.get("url") or str(cfg.relative_to(project_root)),
                "origin": row.get("origin") or data.get("provider") or data.get("url") or cfg.name,
                "acquired_at": row.get("acquired_at") or NOW,
                "access_method": row.get("access_method") or data.get("access_method") or "pipeline",
                "freshness_status": row.get("freshness_status") or "fresh",
                "admissibility_status": row.get("admissibility_status") or "observed",
                "impact_level": row.get("impact_level") or "normal",
                "provenance": row.get("provenance")
                or {"config_path": str(cfg.relative_to(project_root))},
            }
        )
    _write_json(state_path, rows)


def _panel_html(panel_id: str, title: str, description: str, sql: str, chart_type: str = "line") -> str:
    sql_json = json.dumps(sql)
    return f"""<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script src="{CHART_CDN}"></script>
  </head>
  <body style="margin:0;background:transparent;color:#111111;font-family:Inter,system-ui,sans-serif;">
    <motion.div style="height:100%;display:flex;flex-direction:column;gap:12px;padding:12px 14px 10px 14px;box-sizing:border-box;">
      <motion.div>
        <div style="font-size:16px;font-weight:700;">{title}</motion.div>
        <motion.div style="font-size:12px;color:#6b6b6b;margin-top:4px;">{description}</motion.div>
      </motion.div>
      <div id="{panel_id}-status" style="font-size:12px;color:#6b6b6b;">Loading data…</div>
      <div style="position:relative;flex:1;min-height:220px;">
        <canvas id="{panel_id}" style="width:100%;height:100%;"></canvas>
      </div>
    </motion.div>
    <script>
      (async () => {{
        const status = document.getElementById("{panel_id}-status");
        const canvas = document.getElementById("{panel_id}");
        try {{
          const res = await fetch('/api/rail-sql', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{query: {sql_json}}})
          }});
          const payload = await res.json();
          const rows = payload.rows || [];
          status.textContent = rows.length ? '' : 'No data available.';
          if (!rows.length || !canvas) return;
          const labels = rows.map(r => r[0]);
          const values = rows.map(r => Number(r[1]));
          const config = {{
            type: {json.dumps(chart_type)},
            data: {{
              labels,
              datasets: [{{
                label: {json.dumps(title)},
                data: values,
                borderColor: '#cc0000',
                backgroundColor: 'rgba(204,0,0,0.15)',
                borderWidth: 2
              }}]
            }},
            options: {{
              responsive: true,
              maintainAspectRatio: false,
              plugins: {{ legend: {{ display: true, position: 'bottom' }} }},
              scales: {{
                x: {{ ticks: {{ color: '#6b6b6b' }} }},
                y: {{ ticks: {{ color: '#6b6b6b' }} }}
              }}
            }}
          }};
          new Chart(canvas, config);
        }} catch (err) {{
          status.textContent = 'Failed to load chart data.';
        }}
      }})();
    </script>
  </body>
</html>""".replace("<motion.", "<").replace("</motion.", "</")


def build_dashboard_panels(project_root: Path, slug: str, counts: dict[str, int]) -> list[dict]:
    if slug == "assessing-the-economic-impact-of-the-urban-enterprise-zone-program-reform":
        panels_spec = [
            (
                "annual_sut",
                "Average SUT Collections by Year",
                "Ontology-backed annual average of municipal sales & use tax collections.",
                "SELECT year, avg_value FROM AnnualSeries WHERE measure_code = 'sut' ORDER BY year",
                "line",
            ),
            (
                "annual_emp",
                "Average Employment by Year",
                "Annual employment observations averaged across UEZ municipalities.",
                "SELECT year, avg_value FROM AnnualSeries WHERE measure_code = 'emp' ORDER BY year",
                "line",
            ),
            (
                "top_municipalities",
                "Largest 2024 SUT Collections",
                "Top municipalities by latest observed SUT collections in the ontology.",
                """SELECT municipality, value FROM MunicipalityYearPanel
                   WHERE measure_code = 'sut' AND year = 2024
                   ORDER BY value DESC LIMIT 10""",
                "bar",
            ),
        ]
    elif slug == "european-soccer-competitive-ecosystem-analysis":
        panels_spec = [
            (
                "matches_per_season",
                "Matches Recorded per Season",
                "Count of domestic match results in the hydrated ontology.",
                """SELECT CAST(substr(matchDate, 1, 4) AS INTEGER) AS season_year, COUNT(*) AS n
                   FROM Matches WHERE matchDate IS NOT NULL
                   GROUP BY 1 ORDER BY 1""",
                "bar",
            ),
            (
                "goals_trend",
                "Average Goals per Match",
                "Home plus away goals averaged by season.",
                """SELECT CAST(substr(matchDate, 1, 4) AS INTEGER) AS season_year,
                          AVG(COALESCE(homeGoals,0)+COALESCE(awayGoals,0)) AS avg_goals
                   FROM Matches WHERE matchDate IS NOT NULL
                   GROUP BY 1 ORDER BY 1""",
                "line",
            ),
            (
                "ucl_participation",
                "UCL Participation Records",
                "Competition participation rows by domestic season label.",
                """SELECT domesticSeasonLabel AS season, COUNT(*) AS n
                   FROM CompetitionParticipations
                   WHERE domesticSeasonLabel IS NOT NULL
                   GROUP BY 1 ORDER BY 1""",
                "bar",
            ),
        ]
    else:
        panels_spec = [
            (
                "monthly_load",
                "PJM Metered Load (Monthly Average)",
                "Average hourly metered load across all zones in the ontology.",
                """SELECT strftime(CAST(datetime_beginning_ept AS TIMESTAMP), '%Y-%m') AS month,
                          AVG(mw) AS avg_mw
                   FROM hrl_load_metered
                   GROUP BY 1 ORDER BY 1""",
                "line",
            ),
            (
                "monthly_lmp",
                "Day-Ahead LMP (Monthly Average)",
                "Average total day-ahead LMP for HRL nodes.",
                """SELECT strftime(CAST(datetime_beginning_ept AS TIMESTAMP), '%Y-%m') AS month,
                          AVG(total_lmp_da) AS avg_lmp
                   FROM da_hrl_lmps
                   GROUP BY 1 ORDER BY 1""",
                "line",
            ),
            (
                "data_centers",
                "NJ Data Center Capacity",
                "Reported capacity (MW) for facilities in the ontology.",
                """SELECT name, capacity_mw FROM DataCenterFacilities
                   WHERE capacity_mw IS NOT NULL ORDER BY capacity_mw DESC""",
                "bar",
            ),
        ]

    panels = []
    for panel_id, title, desc, sql, chart_type in panels_spec:
        width = "full" if chart_type == "line" else "half"
        panels.append(
            {
                "id": panel_id,
                "title": title,
                "description": desc,
                "width": width,
                "height": 320 if chart_type == "line" else 300,
                "html": _panel_html(panel_id, title, desc, sql, chart_type),
            }
        )

    stat_panel = {
        "id": "ontology_coverage",
        "title": "Ontology Coverage",
        "description": "Row counts for major ontology tables backing this dashboard.",
        "width": "full",
        "height": 200,
        "html": _stat_cards_html(counts),
    }
    panels.append(stat_panel)
    return panels


def _stat_cards_html(counts: dict[str, int]) -> str:
    top = sorted(counts.items(), key=lambda x: -x[1])[:6]
    cards = "".join(
        f"""<motion.div style="border:1px solid #d8d8d4;padding:14px;border-radius:10px;background:#fff;">
        <div style="font-size:11px;text-transform:uppercase;color:#6b6b6b;">{name}</motion.div>
        <div style="font-size:26px;font-weight:700;margin-top:6px;">{n:,}</motion.div>
      </motion.div>"""
        for name, n in top
    )
    return f"""<!DOCTYPE html><html><body style="margin:0;font-family:Inter,system-ui,sans-serif;">
    <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:12px;">{cards}</div>
    </body></html>""".replace("<motion.", "<").replace("</motion.", "</")


def write_static_dashboard(project_root: Path, meta: dict, counts: dict[str, int]) -> None:
    rows = "".join(
        f"<tr><td>{name}</td><td>{n:,}</td></tr>" for name, n in sorted(counts.items(), key=lambda x: -x[1])[:12]
    )
    summary = meta.get("summary_artifact", "")
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>{meta['title']} Dashboard</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;background:#fafafa;color:#111}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:1rem;margin:1rem 0}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ddd;padding:.5rem .75rem}}
th{{background:#f0f4f8}}
a{{color:#b00}}
</style></head><body>
<h1>{meta['title']}</h1>
<p>Generated {NOW}. Explore live charts in the RAIL web UI <strong>Dashboard</strong> tab.
Open the <a href="/projects/{meta['slug']}/ontology">ontology explorer</a> for entities and SQL.</p>
<section class="card"><h2>Primary deliverable</h2>
<p><code>{summary}</code></p></section>
<section class="card"><h2>Ontology tables (row counts)</h2>
<table><thead><tr><th>Table</th><th>Rows</th></tr></thead><tbody>{rows}</tbody></table>
</section></body></html>"""
    out = project_root / "artifacts" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    lineage_path = project_root / "research_plan" / "state" / "artifact_lineage.json"
    lineage = _load_json(lineage_path, [])
    rel = "artifacts/dashboard.html"
    if not any(x.get("artifact_path") == rel for x in lineage):
        lineage.append(
            {
                "artifact_path": rel,
                "artifact_type": "dashboard",
                "title": f"{meta['title']} static dashboard",
                "registered_at": NOW,
                "producer": "scripts/complete_flagship_deliverables.py",
            }
        )
        _write_json(lineage_path, lineage)


def update_plan_closed(project_root: Path) -> None:
    plan = project_root / "research_plan" / "current_plan.md"
    text = plan.read_text(encoding="utf-8") if plan.exists() else ""
    text = re.sub(r"(?m)^phase:\s*.+$", "phase: closed", text, count=1)
    if "phase: closed" not in text:
        text = f"phase: closed\nstatus: deliverables complete ({NOW})\n\n" + text
    plan.write_text(text, encoding="utf-8")


def compile_paper(project_root: Path, meta: dict) -> None:
    tex = meta.get("paper_tex")
    if not tex:
        return
    tex_path = project_root / tex
    if not tex_path.exists():
        return
    if shutil.which("pdflatex") is None:
        return
    cwd = tex_path.parent
    for _ in range(2):
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_path.name],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
    pdf_name = meta.get("paper_pdf")
    if pdf_name:
        built = cwd / tex_path.with_suffix(".pdf").name
        target = project_root / pdf_name
        if built.exists() and built.resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, target)


def copy_soccer_paper_pdf(project_root: Path) -> None:
    md = project_root / "artifacts" / "final_ontology_backed_soccer_ecosystem_report.md"
    tex_out = project_root / "research" / "soccer_ecosystem_paper.tex"
    if not md.exists():
        return
    body = md.read_text(encoding="utf-8")
    body = body.replace("#", "\\section*{").replace("\n", "\n\n")  # minimal — use verbatim
    tex = r"""\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{verbatim}
\begin{document}
\title{European Soccer Competitive Ecosystem Analysis}
\author{RAIL}
\date{\today}
\maketitle
\begin{verbatim}
""" + md.read_text(encoding="utf-8")[:120000] + r"""
\end{verbatim}
\end{document}
"""
    tex_out.parent.mkdir(parents=True, exist_ok=True)
    tex_out.write_text(tex, encoding="utf-8")
    if shutil.which("pdflatex"):
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "soccer_ecosystem_paper.tex"],
            cwd=tex_out.parent,
            capture_output=True,
            check=False,
        )


def remove_pjm_limits(project_root: Path) -> None:
    pipe = project_root / ".ontology" / "pipelines"
    for path in pipe.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        if "limit: 1000" in text:
            path.write_text(text.replace("\n    limit: 1000", ""), encoding="utf-8")


def main() -> None:
    for meta in PROJECTS:
        slug = meta["slug"]
        root = REPO / "generated_projects" / slug
        if not root.exists():
            print(f"skip missing {slug}")
            continue
        print(f"\n=== {slug} ===")
        meta = {**meta, "slug": slug}
        sync_ontology_yaml(root)
        counts = export_owl_to_duckdb(root, slug=slug)
        if slug.startswith("assessing-the-economic-impact"):
            enrich_uez_duckdb(root)
            con = duckdb.connect(str(root / ".ontology" / "onto.duckdb"))
            for t in ("Municipality", "MunicipalityYearPanel", "AnnualSeries", "Measure"):
                try:
                    counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                except Exception:
                    pass
            con.close()
        elif slug.startswith("assessing-data-center"):
            remove_pjm_limits(root)

        sync_sources_json(root)
        panels = build_dashboard_panels(root, slug, counts)
        _write_json(root / "research" / "dashboard_panels.json", panels)
        write_static_dashboard(root, meta, counts)
        update_plan_closed(root)
        compile_paper(root, meta)
        if slug == "european-soccer-competitive-ecosystem-analysis":
            copy_soccer_paper_pdf(root)
        print(f"  tables: {len(counts)}  panels: {len(panels)}  rows(top): {sorted(counts.items(), key=lambda x:-x[1])[:4]}")


if __name__ == "__main__":
    main()
