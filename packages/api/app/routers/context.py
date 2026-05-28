"""
Context / Knowledge Base router.

Handles upload and management of research papers, laws, websites, and reports
that agents can reference before resorting to web search.
"""

import io
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.services.convex_client import convex
from app.services import planner_service


async def _resolve_context_project(project_id: str | None) -> dict[str, Any] | None:
    if not project_id:
        return None

    project = None
    candidate_slugs = [project_id]
    if isinstance(project_id, str) and project_id.startswith("local:"):
        candidate_slugs.append(project_id.removeprefix("local:"))
    for candidate in candidate_slugs:
        try:
            project = await planner_service.get_project_by_slug(candidate)
            if project:
                break
        except Exception:
            project = None

    if not project and not str(project_id).startswith("local:"):
        try:
            project = await convex.query("projects:getById", {"projectId": project_id})
        except Exception:
            project = None

    return project if isinstance(project, dict) else None


async def _context_create_payload_project_fields(project_id: str | None) -> dict[str, str | None]:
    project = await _resolve_context_project(project_id)
    slug = ""
    if isinstance(project, dict):
        slug = str(project.get("slug") or "").strip()
    if not slug and project_id:
        slug = str(project_id).removeprefix("local:").strip()
    return {"projectSlug": slug or None}


async def _sync_context_doc_as_integrity_source(
    *,
    project_id: str | None,
    doc_id: str,
    name: str,
    content: str,
    doc_type: str,
    url: str | None = None,
    file_path_hint: str | None = None,
) -> None:
    """Promote a freshly-created context document into the integrity source
    inventory so downstream claims can reference it with source_key
    `context-<doc_id>`.

    Context entries are first-class evidence — they sit alongside structured
    sources and should be admissible for claim attribution. Before this sync,
    claims that cited context docs failed reference validation because the
    source key wasn't present in research_plan/state/sources.json.
    """
    if not project_id or not doc_id:
        return
    project = await _resolve_context_project(project_id)
    local_repo_path = (project or {}).get("localRepoPath")
    if not local_repo_path:
        return
    root = Path(str(local_repo_path)).resolve()
    if not (root / "rail.yaml").is_file():
        return
    try:
        from rail.integrity import ResearchIntegrityRepo

        repo = ResearchIntegrityRepo(root)
        source_key = f"context-{doc_id}"
        # Preserve the original doc_type — tests assert on it, and the
        # downstream chunk_kind selector uses it to distinguish text/pdf/etc.
        source_type = doc_type
        # For url docs, use the URL as the canonical path and the hostname
        # as the origin; for text/pdf/docx, the human-readable name goes in
        # url_or_path and origin reflects the ingest path.
        if doc_type == "url" and url:
            from urllib.parse import urlparse

            try:
                origin_value = urlparse(url).hostname or f"context:{doc_type}"
            except Exception:
                origin_value = f"context:{doc_type}"
            access_method = "web"
            url_or_path_value = url
        else:
            # File upload: the filename is the canonical path AND origin
            # (operator's local file is the source) and the access method
            # reflects how it arrived. For pasted text the display name fills
            # both slots but the origin keeps the ingest-path qualifier and
            # access stays "manual".
            if file_path_hint:
                url_or_path_value = file_path_hint
                origin_value = file_path_hint
                access_method = "upload"
            else:
                url_or_path_value = name
                origin_value = f"context:{doc_type}"
                access_method = "manual"
        record: dict[str, Any] = {
            "source_key": source_key,
            "source_type": source_type,
            "title": name,
            "url_or_path": url_or_path_value,
            "origin": origin_value,
            "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "access_method": access_method,
            "freshness_status": "fresh",
            "admissibility_status": "observed",
            # Context docs are operator-supplied; they're admissible as
            # evidence but not auto-validated. Promotion to validated should
            # require explicit review.
            "quality_status": "candidate",
            "provenance": {
                "text": content[:2000],
                "context_doc_id": doc_id,
                "ingest_path": "context",
            },
        }
        repo.upsert_source(record)
        # Stamp the chunks' metadata so downstream consumers (UI, search
        # cards) can attribute back to the context doc.
        try:
            chunk_metadata = {
                "source_title": name,
                "source_type": source_type,
                "origin": origin_value,
                "context_doc_id": doc_id,
            }
            chunks = repo.chunks_for_source(source_key)
            mutated = False
            updated_chunks = []
            for chunk in chunks:
                merged = {**(chunk.metadata or {}), **chunk_metadata}
                if merged != chunk.metadata:
                    updated_chunks.append(
                        chunk.model_copy(update={"metadata": merged})
                    )
                    mutated = True
                else:
                    updated_chunks.append(chunk)
            if mutated:
                all_chunks = repo.load_evidence_chunks()
                rest = [c for c in all_chunks if c.source_key != source_key]
                repo.write_evidence_chunks(rest + updated_chunks)
        except Exception:
            pass
    except Exception:
        # Don't fail the context endpoint if the integrity sync hits a
        # validator quirk — the context doc itself is already saved in Convex.
        pass

router = APIRouter(prefix="/context", tags=["context"])


def _extract_pdf(data: bytes) -> str:
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        return "\n\n".join(text_parts)
    except Exception as e:
        raise HTTPException(422, f"Failed to extract PDF text: {e}")


def _extract_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise HTTPException(422, f"Failed to extract DOCX text: {e}")


def _scrape_url(url: str) -> str:
    try:
        import requests
        from bs4 import BeautifulSoup
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:50_000]
    except Exception as e:
        raise HTTPException(422, f"Failed to scrape URL: {e}")


@router.post("/upload")
async def upload_context(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    name: str | None = Form(default=None),
):
    data = await file.read()
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        doc_type = "pdf"
        content = _extract_pdf(data)
    elif ext in (".docx", ".doc"):
        doc_type = "docx"
        content = _extract_docx(data)
    elif ext in (".txt", ".md"):
        doc_type = "text"
        content = data.decode("utf-8", errors="replace")
    else:
        raise HTTPException(415, f"Unsupported file type: {ext}. Use PDF, DOCX, or TXT.")

    payload = {
        "projectId": project_id or None,
        "name": name or filename,
        "type": doc_type,
        "content": content[:100_000],  # cap at 100k chars
        "fileSize": len(data),
    }
    payload.update(await _context_create_payload_project_fields(project_id))
    payload.pop("projectId", None)
    doc_id = await convex.mutation("context:create", payload)
    await _sync_context_doc_as_integrity_source(
        project_id=project_id,
        doc_id=str(doc_id) if doc_id else "",
        name=name or filename,
        content=content,
        doc_type=doc_type,
        file_path_hint=filename,
    )
    return {"id": doc_id, "name": name or filename, "type": doc_type, "size": len(data)}


class AddUrlRequest(BaseModel):
    url: str
    name: str | None = None
    project_id: str | None = None


@router.post("/url")
async def add_url(req: AddUrlRequest):
    content = _scrape_url(req.url)
    payload = {
        "name": req.name or req.url,
        "type": "url",
        "content": content,
        "url": req.url,
    }
    payload.update(await _context_create_payload_project_fields(req.project_id))
    doc_id = await convex.mutation("context:create", payload)
    await _sync_context_doc_as_integrity_source(
        project_id=req.project_id,
        doc_id=str(doc_id) if doc_id else "",
        name=req.name or req.url,
        content=content,
        doc_type="url",
        url=req.url,
    )
    return {"id": doc_id, "name": req.name or req.url, "type": "url"}


class AddTextRequest(BaseModel):
    name: str
    content: str
    project_id: str | None = None


@router.post("/text")
async def add_text(req: AddTextRequest):
    payload = {
        "name": req.name,
        "type": "text",
        "content": req.content[:100_000],
    }
    payload.update(await _context_create_payload_project_fields(req.project_id))
    doc_id = await convex.mutation("context:create", payload)
    await _sync_context_doc_as_integrity_source(
        project_id=req.project_id,
        doc_id=str(doc_id) if doc_id else "",
        name=req.name,
        content=req.content,
        doc_type="text",
    )
    return {"id": doc_id, "name": req.name, "type": "text"}


@router.get("/list")
async def list_context(project_id: str | None = None):
    payload = await _context_create_payload_project_fields(project_id)
    return await convex.query("context:list", payload if payload.get("projectSlug") else {})


@router.delete("/{doc_id}")
async def delete_context(doc_id: str):
    await convex.mutation("context:remove", {"id": doc_id})
    return {"deleted": True}
