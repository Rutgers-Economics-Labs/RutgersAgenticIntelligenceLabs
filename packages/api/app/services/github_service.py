import time
import base64
import hashlib
import hmac
import httpx
import jwt  # PyJWT
from app.core.config import settings

class GitHubService:
    BASE = "https://api.github.com"

    async def _request(self, method: str, repo: str, path: str, *, token: str | None = None, **kwargs):
        auth_token = token or await self.get_installation_token(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method,
                f"{self.BASE}/repos/{repo}{path}",
                headers={
                    "Authorization": f"token {auth_token}",
                    "Accept": "application/vnd.github+json",
                },
                **kwargs,
            )
            resp.raise_for_status()
            return resp

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
        resp = await self._request("GET", repo, f"/contents/{path}", params={"ref": ref})
        data = resp.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def get_file_metadata(self, repo: str, path: str, ref: str = "main") -> dict | None:
        token = await self.get_installation_token(repo)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/repos/{repo}/contents/{path}",
                params={"ref": ref},
                headers={"Authorization": f"token {token}",
                         "Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            raw = base64.b64decode(data["content"]).decode("utf-8")
            return {"sha": data.get("sha"), "content": raw, "path": path}

    async def put_file(self, repo: str, path: str, content: str,
                       message: str, sha: str | None = None) -> dict:
        """Create or update a file. sha required for updates."""
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        body = {"message": message, "content": encoded}
        if sha:
            body["sha"] = sha
        resp = await self._request("PUT", repo, f"/contents/{path}", json=body)
        return {"commit_sha": resp.json()["commit"]["sha"], "branch": "main"}

    async def list_changed_files(self, repo: str, before_sha: str, after_sha: str) -> list[str]:
        """Return list of file paths changed between two commits."""
        resp = await self._request("GET", repo, f"/compare/{before_sha}...{after_sha}")
        return [f["filename"] for f in resp.json().get("files", [])]

    async def get_branch_head(self, repo: str, branch: str) -> str:
        resp = await self._request("GET", repo, f"/git/ref/heads/{branch}")
        return resp.json()["object"]["sha"]

    async def get_commit(self, repo: str, commit_sha: str) -> dict:
        resp = await self._request("GET", repo, f"/git/commits/{commit_sha}")
        return resp.json()

    async def create_blob(self, repo: str, content: str, *, token: str | None = None) -> str:
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        resp = await self._request(
            "POST",
            repo,
            "/git/blobs",
            token=token,
            json={"content": encoded, "encoding": "base64"},
        )
        return resp.json()["sha"]

    async def create_tree(self, repo: str, base_tree_sha: str, tree: list[dict], *, token: str | None = None) -> str:
        resp = await self._request(
            "POST",
            repo,
            "/git/trees",
            token=token,
            json={"base_tree": base_tree_sha, "tree": tree},
        )
        return resp.json()["sha"]

    async def create_commit(self, repo: str, message: str, tree_sha: str, parent_sha: str, *, token: str | None = None) -> str:
        resp = await self._request(
            "POST",
            repo,
            "/git/commits",
            token=token,
            json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )
        return resp.json()["sha"]

    async def update_ref(self, repo: str, branch: str, commit_sha: str, *, token: str | None = None) -> None:
        await self._request(
            "PATCH",
            repo,
            f"/git/refs/heads/{branch}",
            token=token,
            json={"sha": commit_sha, "force": False},
        )

    async def commit_files(self, repo: str, branch: str, files: list[dict], message: str) -> dict:
        token = await self.get_installation_token(repo)
        filtered: list[dict] = []
        for file in files:
            existing = await self.get_file_metadata(repo, file["path"], ref=branch)
            if existing and existing["content"] == file["content"]:
                continue
            filtered.append(file)

        head_sha = await self.get_branch_head(repo, branch)
        if not filtered:
            return {
                "commit_sha": head_sha,
                "branch": branch,
                "changed": False,
                "files": [{"path": f["path"], "changed": False} for f in files],
            }

        commit = await self.get_commit(repo, head_sha)
        base_tree_sha = commit["tree"]["sha"]
        tree_entries = []
        for file in filtered:
            blob_sha = await self.create_blob(repo, file["content"], token=token)
            tree_entries.append({
                "path": file["path"],
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            })

        tree_sha = await self.create_tree(repo, base_tree_sha, tree_entries, token=token)
        commit_sha = await self.create_commit(repo, message, tree_sha, head_sha, token=token)
        await self.update_ref(repo, branch, commit_sha, token=token)
        return {
            "commit_sha": commit_sha,
            "branch": branch,
            "changed": True,
            "files": [{"path": f["path"], "changed": True} for f in filtered],
        }

    def verify_webhook(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify X-Hub-Signature-256 header."""
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

github_service = GitHubService()  # module-level singleton
