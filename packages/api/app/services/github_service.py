import time
import base64
import hashlib
import hmac
import httpx
import jwt  # PyJWT
from app.core.config import settings

class GitHubService:
    BASE = "https://api.github.com"

    def _make_jwt(self) -> str:
        """Generate a GitHub App JWT valid for 10 minutes."""
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": settings.github_app_id}
        return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")

    async def get_installation_id(self, repo: str) -> int:
        """Get the installation ID for owner/repo."""
        owner, name = repo.split("/", 1)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/repos/{owner}/{name}/installation",
                headers={"Authorization": f"Bearer {self._make_jwt()}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return resp.json()["id"]

    async def get_installation_token(self, repo: str) -> str:
        """Generate a short-lived installation token for a repo."""
        installation_id = await self.get_installation_id(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE}/app/installations/{installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {self._make_jwt()}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return resp.json()["token"]

    async def get_file(self, repo: str, path: str, ref: str = "main") -> str:
        """Fetch file content from GitHub Contents API."""
        token = await self.get_installation_token(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/repos/{repo}/contents/{path}",
                params={"ref": ref},
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return base64.b64decode(data["content"]).decode("utf-8")

    async def put_file(self, repo: str, path: str, content: str,
                       message: str, sha: str | None = None) -> dict:
        """Create or update a file. sha required for updates."""
        token = await self.get_installation_token(repo)
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        body = {"message": message, "content": encoded}
        if sha:
            body["sha"] = sha
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self.BASE}/repos/{repo}/contents/{path}",
                json=body,
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return {"commit_sha": resp.json()["commit"]["sha"], "branch": "main"}

    async def list_changed_files(self, repo: str, before_sha: str, after_sha: str) -> list[str]:
        """Return list of file paths changed between two commits."""
        token = await self.get_installation_token(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/repos/{repo}/compare/{before_sha}...{after_sha}",
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            return [f["filename"] for f in resp.json().get("files", [])]

    def verify_webhook(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify X-Hub-Signature-256 header."""
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

github_service = GitHubService()  # module-level singleton
