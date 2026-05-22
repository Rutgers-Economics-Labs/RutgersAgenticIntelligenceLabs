"""
Artifact Service — Track B research artifact management.

Maintains the draft and final artifacts of a research project:
- draft_memo.md
- candidate_findings.md
- verified_findings.md
- final_memo.md
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("research_plan") / "state"

FILES = [
    "draft_memo.md",
    "candidate_findings.md",
    "verified_findings.md",
    "final_memo.md"
]

def ensure_draft_artifacts(project_root: Path) -> None:
    """Initialize the research artifact files if they don't exist."""
    state_dir = project_root / ARTIFACTS_DIR
    state_dir.mkdir(parents=True, exist_ok=True)
    
    for filename in FILES:
        path = state_dir / filename
        if not path.exists():
            content = f"# {filename.replace('_', ' ').replace('.md', '').title()}\n\n"
            if filename == "draft_memo.md":
                content += "Current candidate finding:\n*(None yet)*\n"
            path.write_text(content, encoding="utf-8")
            logger.info(f"Artifacts: Created {path}")

def update_draft_memo(project_root: Path, content: str) -> None:
    """Append or update the draft memo with new findings."""
    path = project_root / ARTIFACTS_DIR / "draft_memo.md"
    if path.exists():
        old_content = path.read_text(encoding="utf-8")
        new_content = f"{old_content}\n\n## Update ({Path.cwd().name})\n{content}\n"
        path.write_text(new_content, encoding="utf-8")
