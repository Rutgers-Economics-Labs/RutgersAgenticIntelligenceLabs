# Work Order 11 — Web Scraping Agent

## Layer
2 — Ingestion Expansion

## Goal
Add a `type: scrape` API config source that fetches a URL, extracts tabular data from the page, and feeds it into the hydration pipeline. An LLM agent handles extraction for unstructured HTML; standard parsing handles clean tables.

## Background
Researchers often find data published as HTML tables on government or research websites with no download link. This work order adds a scraping source type to the engine so these can be declared in YAML and hydrated like any other source.

## Steps

### 1. Add `type: scrape` to `api_runner.py`
File: `packages/engine/engine/api_runner.py`

When `type: scrape`:
- Fetch the URL with `requests.get()`
- Parse HTML with `BeautifulSoup`
- If `table_selector` is set in the config: extract that CSS-selected `<table>` directly via `pd.read_html()`
- If no selector: pass page text to LLM with a prompt asking it to extract the primary table as JSON rows
- Apply `fields` mapping as normal

New YAML config fields for `type: scrape`:
```yaml
type: scrape
url: "https://example.gov/data-table"
table_selector: "table.data-table"   # optional CSS selector
javascript: false                     # if true, use Playwright instead of requests
encoding: utf-8                       # optional
```

### 2. Add Playwright support for JS-rendered pages
Install `playwright` as an optional dependency (add to `pyproject.toml` under `[project.optional-dependencies]`).

When `javascript: true`: use `playwright.sync_api` to render the page before parsing. Fall back gracefully if Playwright is not installed.

### 3. Add LLM extraction fallback
When no `table_selector` is set and `pd.read_html()` finds nothing useful, call the LLM:
```python
prompt = f"Extract the main data table from this page as a JSON array of objects:\n\n{page_text[:8000]}"
```
Parse the JSON response and return as a DataFrame.

New engine dependency: the engine itself never calls an LLM directly. Instead, a new `scrape_runner.py` in the engine wraps the LLM call via an optional env-configured HTTP call to the RAIL API's `/agent/infer-schema` endpoint, or skips LLM extraction entirely and returns an empty DataFrame with a warning if the env var `RAIL_API_URL` is not set.

### 4. Add `type: scrape` validation to `yaml_service.py`
File: `packages/api/app/services/yaml_service.py`

When `type == "scrape"`: require `url`; `table_selector` is optional; `javascript` must be bool if present.

### 5. Add "Scrape URL" quick-add to Configs page
File: `packages/web/app/(dashboard)/configs/page.tsx`

Add a "Scrape URL" button that opens a small modal:
- URL input
- Optional: table CSS selector
- "Preview" button — calls a new `POST /api/v1/configs/scrape-preview` endpoint that fetches the URL and returns the first 5 rows as a preview
- "Generate Config" — calls `POST /agent/infer-schema` with the preview rows as sample
- Saves result like WO-06

### 6. New API endpoint: scrape preview
File: `packages/api/app/routers/configs.py` (add endpoint)

```
POST /api/v1/configs/scrape-preview
Body: { url: str, table_selector?: str }
Returns: { columns: str[], rows: dict[], rowCount: int }
```

### 7. Add `scrape` to agent tool `create_config`
The agent should be able to say "scrape this URL and create a config for it" — update the `create_config` tool description to mention `type: scrape`.

## New Dependencies
- `beautifulsoup4` — add to `packages/api/pyproject.toml` and `packages/engine/pyproject.toml`
- `playwright` — optional, `packages/engine/pyproject.toml` optional-dependencies
- `lxml` — for faster HTML parsing

## Affected Files
- `packages/engine/engine/api_runner.py` — add scrape source type
- `packages/engine/engine/scrape_runner.py` — **create** (LLM extraction helper)
- `packages/api/app/services/yaml_service.py` — add scrape validation
- `packages/api/app/routers/configs.py` — add scrape-preview endpoint
- `packages/web/app/(dashboard)/configs/page.tsx` — add Scrape URL button
- `packages/api/pyproject.toml` — add beautifulsoup4, lxml, playwright (optional)
- `specs/api.md` — update after implementation

## Acceptance Criteria
- [ ] `type: scrape` config with `table_selector` successfully fetches and parses an HTML table
- [ ] LLM fallback triggers when no table is found and returns structured rows
- [ ] `scrape-preview` endpoint returns first 5 rows for a given URL
- [ ] Configs page "Scrape URL" flow produces a valid API config YAML
- [ ] yaml_service validates scrape config correctly
- [ ] Engine handles fetch errors gracefully (404, timeout) without crashing the pipeline
