from __future__ import annotations
import os
from pathlib import Path
from typing import Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.convex_client import convex

router = APIRouter(prefix="/projects", tags=["repo"])

class RepoNode(BaseModel):
    name: str
    path: str
    isDir: bool
    size: Optional[int] = None
    children: Optional[List[RepoNode]] = None

class FileContentResponse(BaseModel):
    path: str
    content: str
    extension: str
    size: int

def _build_tree(root: Path, current: Path, depth: int = 0, max_depth: int = 5) -> RepoNode:
    """Recursively build a tree of RepoNodes."""
    is_dir = current.is_dir()
    node = RepoNode(
        name=current.name,
        path=str(current.relative_to(root)),
        isDir=is_dir,
        size=current.stat().st_size if not is_dir else None
    )

    if is_dir and depth < max_depth:
        children = []
        # Filter out hidden files and common noise
        try:
            for item in sorted(current.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if item.name.startswith(".") and item.name != ".ontology":
                    continue
                if item.name in ("__pycache__", "node_modules", "venv", ".git"):
                    continue
                children.append(_build_tree(root, item, depth + 1, max_depth))
        except PermissionError:
            pass
        node.children = children
    
    return node

@router.get("/{slug}/repo/tree")
async def get_repo_tree(
    slug: str, 
    root_dir: Optional[str] = Query(None, alias="rootDir"),
    max_depth: int = Query(3, alias="maxDepth")
) -> RepoNode:
    """List the project's repository structure."""
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    local_path = project.get("localRepoPath")
    if not local_path:
        raise HTTPException(status_code=400, detail="Project has no localRepoPath configured")
    
    repo_root = Path(local_path).resolve()
    if not repo_root.exists():
        raise HTTPException(status_code=404, detail=f"Local repo path not found: {local_path}")

    target_path = repo_root
    if root_dir:
        target_path = (repo_root / root_dir).resolve()
        if not str(target_path).startswith(str(repo_root)):
             raise HTTPException(status_code=403, detail="Path traversal not allowed")
        if not target_path.exists():
             raise HTTPException(status_code=404, detail=f"Directory not found: {root_dir}")

    return _build_tree(repo_root, target_path, max_depth=max_depth)

@router.get("/{slug}/repo/file")
async def get_repo_file(slug: str, path: str = Query(...)) -> FileContentResponse:
    """Read a specific file from the project's repository."""
    project = await convex.query("projects:getBySlug", {"slug": slug})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    local_path = project.get("localRepoPath")
    if not local_path:
        raise HTTPException(status_code=400, detail="Project has no localRepoPath configured")
    
    repo_root = Path(local_path).resolve()
    file_path = (repo_root / path).resolve()

    if not str(file_path).startswith(str(repo_root)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read file: {e}")

    return FileContentResponse(
        path=path,
        content=content,
        extension=file_path.suffix,
        size=file_path.stat().st_size
    )
