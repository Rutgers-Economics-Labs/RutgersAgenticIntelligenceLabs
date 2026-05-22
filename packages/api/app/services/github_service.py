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

    async def get_org_installation_token(self, org: str) -> str:
        """Generate a short-lived installation token scoped to an org (for repo creation)."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE}/orgs/{org}/installation",
                headers={"Authorization": f"Bearer {self._make_jwt()}",
                         "Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            installation_id = resp.json()["id"]
            resp2 = await client.post(
                f"{self.BASE}/app/installations/{installation_id}/access_tokens",
                headers={"Authorization": f"Bearer {self._make_jwt()}",
                         "Accept": "application/vnd.github+json"},
            )
            resp2.raise_for_status()
            return resp2.json()["token"]

    async def create_repo(self, name: str, description: str = "", private: bool = True, org: str | None = None) -> dict:
        """Create a new GitHub repo under the org. Returns {full_name, html_url, clone_url}."""
        from app.core.config import settings
        target_org = org or settings.github_app_org
        token = await self.get_org_installation_token(target_org)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE}/orgs/{target_org}/repos",
                headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
                json={"name": name, "description": description, "private": private, "auto_init": False},
            )
            resp.raise_for_status()
            data = resp.json()
            return {"full_name": data["full_name"], "html_url": data["html_url"], "clone_url": data["clone_url"]}

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
            raw_bytes = base64.b64decode(data["content"])
            try:
                raw = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw = None
            return {"sha": data.get("sha"), "content": raw, "content_bytes": raw_bytes, "path": path}

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

    async def create_blob(self, repo: str, content: str | bytes, *, token: str | None = None) -> str:
        content_bytes = content.encode("utf-8") if isinstance(content, str) else content
        encoded = base64.b64encode(content_bytes).decode("utf-8")
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
            incoming_bytes = (
                file["content"].encode("utf-8")
                if isinstance(file["content"], str)
                else file["content"]
            )
            if existing:
                remote_bytes = existing.get("content_bytes")
                if remote_bytes is None and existing.get("content") is not None:
                    remote_value = existing["content"]
                    remote_bytes = (
                        remote_value.encode("utf-8")
                        if isinstance(remote_value, str)
                        else remote_value
                    )
                if remote_bytes == incoming_bytes:
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

        # Hoisted so the helper below can build new blobs against fresh paths
        # during a ref-race retry.
        async def _build_commit(parent_sha: str) -> str:
            parent_commit = await self.get_commit(repo, parent_sha)
            base_tree_sha = parent_commit["tree"]["sha"]
            tree_entries: list[dict] = []
            for file in filtered:
                blob_sha = await self.create_blob(repo, file["content"], token=token)
                tree_entries.append(
                    {
                        "path": file["path"],
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    }
                )
            tree_sha = await self.create_tree(repo, base_tree_sha, tree_entries, token=token)
            return await self.create_commit(repo, message, tree_sha, parent_sha, token=token)

        commit_sha = await _build_commit(head_sha)
        try:
            await self.update_ref(repo, branch, commit_sha, token=token)
        except httpx.HTTPStatusError as exc:
            # GitHub ref-race: another process advanced the branch between
            # our get_branch_head and our update_ref. GitHub returns 422 in
            # this case. Retry once against the new head, then re-check
            # whether the remote already matches our intended content
            # (someone else may have written the same payload concurrently).
            if exc.response.status_code != 422:
                raise
            new_head_sha = await self.get_branch_head(repo, branch)
            commit_sha = await _build_commit(new_head_sha)
            try:
                await self.update_ref(repo, branch, commit_sha, token=token)
            except httpx.HTTPStatusError as retry_exc:
                if retry_exc.response.status_code != 422:
                    raise
                # If the remote content already matches what we wanted at
                # the (now-newer) head, treat the race as a no-op rather
                # than failing — another process beat us with the same
                # payload. We re-read get_branch_head so the metadata
                # check is against the freshest commit.
                head_after = await self.get_branch_head(repo, branch)
                all_match = True
                for file in filtered:
                    remote = await self.get_file_metadata(repo, file["path"], ref=head_after)
                    if not remote:
                        all_match = False
                        break
                    incoming_bytes = (
                        file["content"].encode("utf-8")
                        if isinstance(file["content"], str)
                        else file["content"]
                    )
                    remote_bytes = remote.get("content_bytes")
                    if remote_bytes is None and "content" in remote:
                        remote_value = remote["content"]
                        remote_bytes = (
                            remote_value.encode("utf-8")
                            if isinstance(remote_value, str)
                            else remote_value
                        )
                    if remote_bytes != incoming_bytes:
                        all_match = False
                        break
                if not all_match:
                    raise
                return {
                    "commit_sha": head_after,
                    "branch": branch,
                    "changed": False,
                    "files": [{"path": f["path"], "changed": False} for f in filtered],
                }

        return {
            "commit_sha": commit_sha,
            "branch": branch,
            "changed": True,
            "files": [{"path": f["path"], "changed": True} for f in filtered],
        }

    async def merge_branch(
        self,
        repo: str,
        base: str,
        head: str,
        *,
        commit_message: str | None = None,
        token: str | None = None,
    ) -> dict:
        """Merge `head` branch into `base` via the GitHub merges API.

        Returns the merge commit object or raises on conflict / missing ref.
        """
        message = commit_message or f"chore(autopilot): merge audited workspace branch {head} into {base}"
        resp = await self._request(
            "POST",
            repo,
            "/merges",
            token=token,
            json={"base": base, "head": head, "commit_message": message},
        )
        if resp.status_code == 204:
            return {"sha": None, "merged": False, "message": "Already up to date"}
        return resp.json()

    def verify_webhook(self, payload_bytes: bytes, signature: str) -> bool:
        """Verify X-Hub-Signature-256 header."""
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

github_service = GitHubService()  # module-level singleton
