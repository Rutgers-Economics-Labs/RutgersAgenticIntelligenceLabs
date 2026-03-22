# Work Order 10 — Semantic Search

## Goal
Add embedding-based semantic search to the Explorer, so researchers can find entities by meaning rather than exact keyword match (e.g. "coastal counties" finds Hudson, Monmouth, Cape May).

## Current State
`GET /api/v1/ontology/search` does keyword matching on `ind.name` and `ind.hasName`. There is no embedding layer.

## Steps

### 1. Choose vector store
Use `sqlite-vec` (SQLite extension for vectors, zero external dependencies) or `hnswlib` (in-memory ANN index, fast). Recommend `sqlite-vec` for persistence across restarts.

Install: `pip install sqlite-vec` (add to `pyproject.toml`).

### 2. Build the embedding index after hydration
New file: `packages/api/app/services/embedding_service.py`

```python
async def build_index(db_path: str) -> None:
    """Embed all entity names+descriptions and store in a sqlite-vec table."""

async def search(query: str, top_k: int = 20, types: list[str] | None = None) -> list[dict]:
    """Embed query, find nearest neighbors, return entity summaries."""

def is_ready() -> bool
```

Embedding model: use LiteLLM's `aembedding()` call (supports OpenAI `text-embedding-3-small`, Cohere, etc.). Fall back to a local `sentence-transformers` model if no embedding API key is configured.

Each entity is embedded as: `"{class_name}: {hasName or id}. {key_properties_as_text}"`.

Store index in `{engine_root}/ontology/embeddings.db`.

### 3. Trigger index build after hydration
In `hydration_worker.py`, after the DuckDB export:
```python
try:
    from app.services import embedding_service
    await embedding_service.build_index(db_key)
except Exception as e:
    await _log(job_id, "warn", f"[job] Embedding index failed (non-fatal): {e}", seq=seq)
```

### 4. New API endpoint
In `packages/api/app/routers/ontology.py`, add:

```
GET /api/v1/ontology/semantic-search?q=...&types=...&limit=20
```

Delegates to `embedding_service.search(q, top_k, types)`.

### 5. Frontend: toggle in Explorer
In `packages/web/app/(dashboard)/explorer/page.tsx`:
- Add a "Semantic" / "Keyword" toggle next to the search input
- When "Semantic" is active, call a new `ontology.semanticSearch(q, types)` function in `lib/api.ts` instead of the paginated instances endpoint
- Show results as a flat list (no pagination — semantic search returns top-K)

### 6. Add `semanticSearch` to `lib/api.ts`
```typescript
export const ontology = {
  ...,
  semanticSearch: (q: string, types?: string[], limit = 20) =>
    req<EntitySummary[]>(`/ontology/semantic-search?q=${encodeURIComponent(q)}${types ? `&types=${types.join(",")}` : ""}&limit=${limit}`)
}
```

### 7. Add env var for embedding model
```
EMBEDDING_MODEL=text-embedding-3-small   # default; requires OPENAI_API_KEY
# or
EMBEDDING_MODEL=local                    # uses sentence-transformers/all-MiniLM-L6-v2
```

Add `embedding_model: str = "text-embedding-3-small"` to `app/core/config.py`.

## Affected Files
- `packages/api/app/services/embedding_service.py` — **create**
- `packages/api/app/services/hydration_worker.py` — add index build call
- `packages/api/app/routers/ontology.py` — add semantic search endpoint
- `packages/api/app/core/config.py` — add `embedding_model` field
- `packages/api/pyproject.toml` — add `sqlite-vec` dependency
- `packages/web/lib/api.ts` — add `ontology.semanticSearch()`
- `packages/web/app/(dashboard)/explorer/page.tsx` — add semantic toggle
- `specs/api.md` — update after implementation

## Acceptance Criteria
- [ ] After hydration, `embeddings.db` is created alongside `onto.duckdb`
- [ ] `GET /ontology/semantic-search?q=coastal+counties` returns relevant counties
- [ ] Explorer semantic toggle works and shows ranked results
- [ ] Index build failure is non-fatal (logs a warning, hydration still succeeds)
- [ ] Works with both OpenAI embedding API and local sentence-transformers fallback
