"""
Context / Knowledge Base router.

Handles upload and management of research papers, laws, websites, and reports
that agents can reference before resorting to web search.
"""

import io
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.services.convex_client import convex

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

    doc_id = await convex.mutation("context:create", {
        "projectId": project_id or None,
        "name": name or filename,
        "type": doc_type,
        "content": content[:100_000],  # cap at 100k chars
        "fileSize": len(data),
    })
    return {"id": doc_id, "name": name or filename, "type": doc_type, "size": len(data)}


class AddUrlRequest(BaseModel):
    url: str
    name: str | None = None
    project_id: str | None = None


@router.post("/url")
async def add_url(req: AddUrlRequest):
    content = _scrape_url(req.url)
    doc_id = await convex.mutation("context:create", {
        "projectId": req.project_id or None,
        "name": req.name or req.url,
        "type": "url",
        "content": content,
        "url": req.url,
    })
    return {"id": doc_id, "name": req.name or req.url, "type": "url"}


class AddTextRequest(BaseModel):
    name: str
    content: str
    project_id: str | None = None


@router.post("/text")
async def add_text(req: AddTextRequest):
    doc_id = await convex.mutation("context:create", {
        "projectId": req.project_id or None,
        "name": req.name,
        "type": "text",
        "content": req.content[:100_000],
    })
    return {"id": doc_id, "name": req.name, "type": "text"}


@router.get("/list")
async def list_context(project_id: str | None = None):
    return await convex.query("context:list", {"projectId": project_id} if project_id else {})


@router.delete("/{doc_id}")
async def delete_context(doc_id: str):
    await convex.mutation("context:remove", {"id": doc_id})
    return {"deleted": True}
