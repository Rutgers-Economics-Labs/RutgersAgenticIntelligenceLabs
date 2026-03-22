# Work Order 27 — Export Formats

## Layer
6 — Reproducibility and Sharing

## Goal
Allow researchers to export any analysis result in publication-ready formats: Markdown report, LaTeX table, CSV data, and PNG figures.

## Steps

### 1. Export service
File: `packages/api/app/services/export_service.py`

```python
def to_markdown(result: dict) -> str:
    """
    Convert an AnalysisResult dict to a markdown document.
    Tables → markdown tables, metrics → key-value list, charts → [Figure omitted],
    text sections → paragraphs.
    """

def to_latex(result: dict) -> str:
    """
    Convert coefficient tables and metrics to LaTeX tabular environment.
    Wraps in \\begin{table}...\\end{table} with \\caption from result title.
    """

def to_csv(table_section: dict) -> str:
    """Convert a single 'table' section to CSV string."""

def to_png_figures(result: dict) -> list[bytes]:
    """
    Re-render any chart sections to matplotlib PNG.
    Returns list of PNG bytes, one per chart section.
    """
```

### 2. Export API endpoints
File: `packages/api/app/routers/export.py`

```
POST /api/v1/export/markdown     body: {run_id} or {result: AnalysisResult}
POST /api/v1/export/latex        same
POST /api/v1/export/csv          body: {run_id, section_index: int}
POST /api/v1/export/figures      body: {run_id} → zip of PNGs
POST /api/v1/export/bundle       body: {run_id} → zip with .md + .tex + CSVs + PNGs
```

All endpoints return file downloads with appropriate `Content-Disposition` headers.

### 3. LaTeX table format
For coefficient tables, output:
```latex
\begin{table}[htbp]
  \centering
  \caption{Coefficient Table}
  \begin{tabular}{lrrrr}
    \hline
    Variable & Coef & SE & t & p \\
    \hline
    ...rows...
    \hline
  \end{tabular}
\end{table}
```

Significance stars: `***` p<0.01, `**` p<0.05, `*` p<0.1.

### 4. Export buttons in workspace UI
In the result area of each workspace cell, add an "Export" dropdown with options:
- Download as Markdown
- Download as LaTeX
- Download CSV (for table cells)
- Download Figure (for chart cells)
- Download Bundle (all formats as .zip)

### 5. Markdown report template
The markdown export should be a complete research note:

```markdown
# {result.title}

**Generated:** {timestamp}
**Model:** {provenance.modelId}
**Data Version:** {provenance.ontologyVersion[:8]}

## Results

{sections rendered as markdown}

## Methodology

{provenance.agentMessages summary}

## Data Sources

{provenance.pipelineConfigs list}
```

## Affected Files
- `packages/api/app/services/export_service.py` — **create**
- `packages/api/app/routers/export.py` — **create**
- `packages/api/app/main.py` — register router
- `packages/web/app/(dashboard)/workspace/page.tsx` — export dropdown on result cells
- `specs/api.md` — document export routes

## Acceptance Criteria
- [ ] Markdown export renders all section types (metrics, table, text, chart placeholder)
- [ ] LaTeX export produces valid `.tex` with significance stars in coefficient tables
- [ ] CSV export downloads a clean comma-delimited file from any table section
- [ ] Bundle download is a valid `.zip` with all formats included
- [ ] Export buttons are visible in the workspace UI per cell
