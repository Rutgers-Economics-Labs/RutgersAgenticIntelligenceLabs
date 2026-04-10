# Context & Knowledge Management

RAIL manages context at two levels: the **Unstructured Knowledge Base** (documents) and the **Structured Context Layer** (ontology-derived data slices). The **Context Assembly Pipeline** orchestrates both to provide agents with a precise operational context for every query.

The **knowledge base** is a per-project document store that agents can search before resorting to web queries or admitting a knowledge gap. It holds research papers, regulatory filings, policy documents, reports, and compiled analysis notes.

---

## Purpose

Projects work with public data — unemployment statistics, GDP figures, census counts. But researchers also need context: Why did unemployment spike in this county in 2020? What does state policy say about housing subsidies? What did the Fed's 2023 annual report say about regional labor markets?

The knowledge base bridges structured data (ontology/DuckDB) and unstructured knowledge (documents). Both the Q&A agent and the project setup agent can search it via `search_context` and write to it via `save_to_knowledge_base`.

---

## API Routes — `/api/v1/context`

Router: `packages/api/app/routers/context.py`

| Method | Path | Body / Params | Returns |
|--------|------|--------------|---------|
| POST | `/upload` | multipart: `file`, `project_id?`, `name?` | `{id, name, type, size}` |
| POST | `/url` | `{url, name?, project_id?}` | `{id, name, type}` |
| POST | `/text` | `{name, content, project_id?}` | `{id, name, type}` |
| GET | `/list` | `project_id?` | list of document records |
| DELETE | `/{doc_id}` | — | `{deleted: true}` |

---

## Document Ingestion

### `POST /upload` — File Upload

Accepts PDF, DOCX, DOC, TXT, and MD files.

| Extension | Extraction method |
|-----------|------------------|
| `.pdf` | `pdfplumber` — extracts text from all pages |
| `.docx` / `.doc` | `python-docx` — extracts paragraph text |
| `.txt` / `.md` | UTF-8 decode |

Content is capped at **100,000 characters** per document. The raw bytes are not stored — only the extracted text is saved to Convex.

### `POST /url` — Web URL

Fetches the URL with a standard browser User-Agent, parses HTML with BeautifulSoup, strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>` tags, and saves plain text up to 50,000 characters.

### `POST /text` — Raw Text

Accepts arbitrary text directly (no file needed). Useful for saving compiled analysis, synthesis notes, or agent-generated content. Cap at 100,000 characters.

---

## Convex Table — `contextDocuments`

| Field | Type | Notes |
|-------|------|-------|
| `projectId` | string? | Scoped to a project, or null for global documents |
| `name` | string | Document title (filename or user-provided) |
| `type` | string | `"pdf"` \| `"docx"` \| `"url"` \| `"text"` |
| `content` | string | Extracted text — max 100k chars |
| `url` | string? | Source URL (only for `type: "url"`) |
| `fileSize` | number? | Original file size in bytes (only for file uploads) |
| `createdAt` | number | ms timestamp |
| `updatedAt` | number | ms timestamp |

**Scoping:** Documents with `projectId` are only returned when querying for that project. Documents with no `projectId` are global (returned for all projects).

---

## Agent Integration — `search_context` Tool

Both the Q&A agent and the project setup agent can call `search_context`:

```json
{
  "name": "search_context",
  "args": {
    "query": "state unemployment insurance policy 2022",
    "project_id": "nj-economics"
  }
}
```

**Search behavior (current):** Case-insensitive substring match on `content` and `name`. Returns up to 5 documents with a 600-character snippet centered around the first match.

**Planned:** Embedding-based semantic search using `embedding_service.py` for better recall on paraphrased queries.

### `save_to_knowledge_base` Tool

Both agents can also write to the knowledge base:

```json
{
  "name": "save_to_knowledge_base",
  "args": {
    "name": "NJ Unemployment Trends Summary 2024",
    "content": "Based on analysis of Census ACS5 and BLS LAU data...",
    "project_id": "nj-economics"
  }
}
```

This calls `POST /context/text` internally and saves the content as a `type: "text"` document.

---

## Frontend — `/context`

The knowledge base page at `/context` (project-scoped) provides a document manager.

**Layout:**
- Upload area (drag-and-drop or file picker) for PDF/DOCX/TXT
- URL input field with "Fetch" button
- Document list showing: name, type badge, character count, upload date
- Delete button per document
- Inline text content preview (expandable)

**Planned route:** `/[project]/context` in the new project-scoped routing model.

**Document limits (planned):** No hard limit per project, but the UI will show total character count and warn at 500k chars (search quality degrades with very large corpora).

---

## Relationship to Other Components

| Component | Role |
|-----------|------|
| Q&A agent (`/questions`) | Calls `search_context` to supplement SQL answers with background knowledge |
| Project setup agent (`/project-agent`) | Calls `save_to_knowledge_base` after creating configs; reads context to answer "what data do we have?" |
| Research agent (`/agent`) | May call `search_context` for deep research workflows (planned) |
| `contextDocuments` Convex table | Stores all documents — the API is a thin wrapper over this |

---

## The Context Layer & Assembly Pipeline

The **Context Layer** is the "operational slice" of the platform. Unlike the full serving layer (DuckDB), it contains only the entities, relationships, and metadata relevant to the current user query.

### The Assembly Pipeline Flow

1.  **Request**: User asks a natural language question.
2.  **Planner (Role)**: Analyzes the question and produces a **Manifest** of required ontology classes, identifiers, and time ranges.
3.  **Coverage (Role)**: Correlates the Manifest with the **Metadata Layer** to determine if the data exists in the Serving Layer.
4.  **Assembler (Service)**: Gathers the matching SQL views from DuckDB and document fragments from the Knowledge Base.
5.  **Bundle**: Produces a **`StructuredContextBundle`** (a signed manifest and data slice).

### Structured Context Bundle Schema

The bundle is a JSON object injected into the agent's work session:

```json
{
  "project_status": {
    "hydrated": true,
    "last_sync": "2024-01-15T08:00:00Z"
  },
  "ontology_slice": {
    "classes": ["County", "UnemploymentRate"],
    "ddl": "CREATE VIEW county_context AS SELECT ...",
    "relationships": ["measuredFor"]
  },
  "knowledge_fragments": [
    {"doc_id": "policy_2022", "snippet": "..."}
  ],
  "serving_artifact_hash": "sha256:77d..."
}
```

## Design Constraints

- **No vector database.** Search is keyword-based using substring matching. This is intentional for v1 — adding embedding search is a planned improvement using `embedding_service.py`.
- **Context Locking.** Agents cannot access data outside the structured bundle. This prevents leakage and "hallucination-by-overexposure."
- **100k char cap.** Long documents are truncated. For very long documents (book-length reports), users should upload specific chapters or sections.
- **No versioning.** Documents are replaced by deleting and re-uploading. Versioning is not planned.
