# Work Order 12 — PDF and Document Parsing

## Layer
2 — Ingestion Expansion

## Goal
Add `type: pdf` and `type: docx` API config sources that extract tabular data and statistical claims from documents, feeding them into the hydration pipeline.

## Background
Economic research is often locked in PDFs (Federal Reserve reports, BLS publications, academic papers). This work order lets researchers point the engine at a document URL or file path and extract structured data from it.

## Steps

### 1. Add `type: pdf` to `api_runner.py`

New YAML config fields:
```yaml
type: pdf
path: "sources/fed_report_2023.pdf"     # local file
# or
url: "https://www.federalreserve.gov/report.pdf"  # remote download
extraction_mode: tables                  # "tables" | "prose" | "both"
pages: "1-10"                           # optional page range
table_index: 0                          # which table on the page (0-indexed), optional
```

When `extraction_mode: tables`:
- Use `pdfplumber` to extract tables page by page
- If `table_index` set, return that table only; otherwise concatenate all tables
- Apply `fields` mapping as normal

When `extraction_mode: prose`:
- Extract full text via `pdfplumber`
- Pass to LLM with prompt: "Extract all numerical data points and their labels from this text as a JSON array of {label, value, unit, date} objects."
- Convert LLM output to DataFrame

When `extraction_mode: both`: run both, merge results.

### 2. Add `type: docx`

Same as PDF but using `python-docx` for `.docx` files. Tables extracted natively; prose extraction via LLM.

### 3. Remote PDF download
If `url` is set instead of `path`: download the PDF to `RAIL_CACHE_DIR/{hash}.pdf` before parsing. Cache by URL hash so repeat runs don't re-download.

### 4. Upload-and-parse flow in the UI
File: `packages/web/app/(dashboard)/configs/page.tsx`

Add a "Upload Document" button alongside the existing file upload. Accepts `.pdf` and `.docx`. On upload:
1. Sends file to `POST /api/v1/storage/upload` (existing endpoint)
2. Calls a new `POST /api/v1/configs/doc-preview` endpoint with the storage key
3. Returns first table or first 10 prose extractions as a preview
4. User can generate a full config from the preview (same flow as WO-06/WO-11)

### 5. New API endpoint: doc-preview
File: `packages/api/app/routers/configs.py`

```
POST /api/v1/configs/doc-preview
Body: { storage_key: str, extraction_mode: "tables" | "prose", pages?: str }
Returns: { columns: str[], rows: dict[], rowCount: int, source_text?: str }
```

### 6. yaml_service validation
When `type == "pdf"` or `type == "docx"`:
- Require either `path` or `url` (not both)
- `extraction_mode` must be one of `tables`, `prose`, `both`
- `pages` must match pattern `\d+(-\d+)?` if present

## New Dependencies
- `pdfplumber` — PDF table and text extraction
- `python-docx` — Word document parsing
Add both to `packages/engine/pyproject.toml` and `packages/api/pyproject.toml`.

## Affected Files
- `packages/engine/engine/api_runner.py` — add pdf/docx source types
- `packages/api/app/services/yaml_service.py` — add validation rules
- `packages/api/app/routers/configs.py` — add doc-preview endpoint
- `packages/web/app/(dashboard)/configs/page.tsx` — add Upload Document button
- `packages/engine/pyproject.toml` — add pdfplumber, python-docx
- `packages/api/pyproject.toml` — add pdfplumber, python-docx
- `specs/api.md` — update after implementation

## Acceptance Criteria
- [ ] A PDF URL with a clean table produces a populated DataFrame via `type: pdf, extraction_mode: tables`
- [ ] Prose extraction returns structured JSON rows from a paragraph describing statistics
- [ ] Remote PDF is cached and not re-downloaded on second run
- [ ] `doc-preview` endpoint returns first 5 rows from an uploaded PDF
- [ ] Pipeline using a PDF source hydrates successfully end-to-end
- [ ] Malformed or password-protected PDFs fail gracefully with a clear error message
