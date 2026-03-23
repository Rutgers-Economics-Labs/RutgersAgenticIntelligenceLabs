"""ArtifactSaver — uploads outputs to a job via POST /jobs/{job_id}/artifacts."""
from __future__ import annotations
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import RailClient

_API_BASE = "/api/v1"


class ArtifactSaver:
    def __init__(self, client: "RailClient", job_id: str) -> None:
        self._client = client
        self._job_id = job_id

    def _upload(self, name: str, artifact_type: str, content: bytes, mime_type: str) -> dict:
        url = f"{self._client._base}/jobs/{self._job_id}/artifacts"
        resp = self._client._session.post(
            url,
            files={"file": (name, content, mime_type)},
            data={"name": name, "artifact_type": artifact_type, "mime_type": mime_type},
        )
        resp.raise_for_status()
        return resp.json()

    def save_text(self, text: str, name: str = "output.txt") -> dict:
        """Save a plain text or markdown string as an artifact."""
        if not name.endswith((".txt", ".md")):
            name = name if "." in name else name + ".txt"
        return self._upload(name, "text", text.encode("utf-8"), "text/plain")

    def save_figure(self, fig, name: str = "figure") -> dict:
        """Save a matplotlib Figure as a PNG artifact."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
        buf.seek(0)
        fname = name if name.endswith(".png") else name + ".png"
        return self._upload(fname, "image", buf.getvalue(), "image/png")

    def save_image(self, img, name: str = "image") -> dict:
        """Save a PIL Image as a PNG artifact."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        fname = name if name.endswith(".png") else name + ".png"
        return self._upload(fname, "image", buf.getvalue(), "image/png")

    def save_model(self, model, name: str = "model") -> dict:
        """Serialize a scikit-learn (or any joblib-compatible) model as an artifact."""
        import joblib
        buf = io.BytesIO()
        joblib.dump(model, buf)
        buf.seek(0)
        fname = name if name.endswith(".joblib") else name + ".joblib"
        return self._upload(fname, "model", buf.getvalue(), "application/octet-stream")

    def save_file(self, path: str, name: str | None = None) -> dict:
        """Upload any local file as an artifact."""
        import mimetypes
        from pathlib import Path
        p = Path(path)
        fname = name or p.name
        mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        return self._upload(fname, "file", p.read_bytes(), mime)
