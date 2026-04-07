"""GitHub API service for fetching repository contents."""

import base64
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()

BASE_URL = "https://api.github.com"


@dataclass
class ModuleFileInfo:
    """Info about a fetched module file."""
    file_type: str  # workflow, agent, resource
    file_path: str  # e.g. "workflows/planning@1.0.0.yaml"
    content: str    # Raw YAML content
    sha: str        # Git blob SHA


class GitHubApiService:
    """Fetches repo contents via GitHub Contents API."""

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def list_user_repos(
        self, token: str, page: int = 1, per_page: int = 50
    ) -> list[dict]:
        """GET /user/repos — list repos accessible to the authenticated user."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{BASE_URL}/user/repos",
                headers=self._headers(token),
                params={
                    "sort": "updated",
                    "per_page": per_page,
                    "page": page,
                    "visibility": "all",
                },
            )
            resp.raise_for_status()
            return [
                {
                    "owner": r["owner"]["login"],
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "description": r.get("description") or "",
                    "private": r["private"],
                    "stargazers_count": r.get("stargazers_count", 0),
                    "default_branch": r.get("default_branch", "main"),
                    "html_url": r.get("html_url", ""),
                }
                for r in resp.json()
            ]

    async def get_repo_info(
        self, token: str, owner: str, name: str
    ) -> Optional[dict]:
        """GET /repos/{owner}/{name} — repo metadata."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{BASE_URL}/repos/{owner}/{name}",
                headers=self._headers(token),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            r = resp.json()
            return {
                "owner": r["owner"]["login"],
                "name": r["name"],
                "full_name": r["full_name"],
                "description": r.get("description") or "",
                "private": r["private"],
                "default_branch": r.get("default_branch", "main"),
            }

    async def list_directory(
        self, token: str, owner: str, name: str, path: str, branch: str = "main",
        *, _client: httpx.AsyncClient | None = None,
    ) -> list[dict]:
        """GET /repos/{owner}/{name}/contents/{path}?ref={branch}"""
        async def _do(client: httpx.AsyncClient) -> list[dict]:
            resp = await client.get(
                f"{BASE_URL}/repos/{owner}/{name}/contents/{path}",
                headers=self._headers(token),
                params={"ref": branch},
            )
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                return []
            return [
                {"name": item["name"], "path": item["path"], "sha": item["sha"], "type": item["type"]}
                for item in data
            ]
        if _client:
            return await _do(_client)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await _do(client)

    async def get_file_content(
        self, token: str, owner: str, name: str, path: str, branch: str = "main",
        *, _client: httpx.AsyncClient | None = None,
    ) -> Optional[tuple[str, str]]:
        """GET /repos/{owner}/{name}/contents/{path}?ref={branch}

        Returns (decoded_content, sha) or None if not found.
        """
        async def _do(client: httpx.AsyncClient) -> Optional[tuple[str, str]]:
            resp = await client.get(
                f"{BASE_URL}/repos/{owner}/{name}/contents/{path}",
                headers=self._headers(token),
                params={"ref": branch},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            if data.get("type") != "file":
                return None
            content_b64 = data.get("content", "")
            decoded = base64.b64decode(content_b64).decode("utf-8")
            return decoded, data["sha"]
        if _client:
            return await _do(_client)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await _do(client)

    async def get_manifest(
        self, token: str, owner: str, name: str, branch: str = "main"
    ) -> Optional[dict]:
        """Fetch + parse vela.yaml from repo root. Returns None if not found."""
        import yaml

        result = await self.get_file_content(token, owner, name, "vela.yaml", branch)
        if not result:
            return None
        content, _ = result
        try:
            return yaml.safe_load(content)
        except Exception as e:
            logger.warning("github.manifest_parse_error", owner=owner, name=name, error=str(e))
            return None

    async def create_repo(
        self, token: str, name: str, description: str = "", private: bool = True,
    ) -> dict:
        """POST /user/repos — create a new GitHub repository.

        auto_init=true ensures an initial commit so the default branch exists.
        Returns: {owner, name, full_name, description, private, default_branch, html_url}
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.post(
                    f"{BASE_URL}/user/repos",
                    headers=self._headers(token),
                    json={
                        "name": name,
                        "description": description,
                        "private": private,
                        "auto_init": True,
                    },
                )
                resp.raise_for_status()
                r = resp.json()
                return {
                    "owner": r["owner"]["login"],
                    "name": r["name"],
                    "full_name": r["full_name"],
                    "description": r.get("description") or "",
                    "private": r["private"],
                    "default_branch": r.get("default_branch", "main"),
                    "html_url": r.get("html_url", ""),
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 422:
                    return {"error": "Repository name already exists or is invalid"}
                return {"error": f"GitHub API error: {e.response.status_code}"}

    async def create_or_update_file(
        self, token: str, owner: str, name: str, path: str,
        content: str, message: str, sha: str | None = None,
        branch: str = "main",
    ) -> dict:
        """PUT /repos/{owner}/{name}/contents/{path} — create or update a file.

        Content is base64-encoded internally. sha=None → create, sha present → update.
        Returns: {path, sha, commit_sha}
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            body: dict = {
                "message": message,
                "content": base64.b64encode(content.encode()).decode(),
                "branch": branch,
            }
            if sha is not None:
                body["sha"] = sha

            try:
                resp = await client.put(
                    f"{BASE_URL}/repos/{owner}/{name}/contents/{path}",
                    headers=self._headers(token),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "path": data["content"]["path"],
                    "sha": data["content"]["sha"],
                    "commit_sha": data["commit"]["sha"],
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 409:
                    return {"error": "SHA conflict — file was modified, sync first"}
                return {"error": f"GitHub API error: {e.response.status_code}"}

    async def delete_file(
        self, token: str, owner: str, name: str, path: str,
        sha: str, message: str, branch: str = "main",
    ) -> dict:
        """DELETE /repos/{owner}/{name}/contents/{path} — delete a file.

        Returns: {path, deleted: true, commit_sha}
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.request(
                    "DELETE",
                    f"{BASE_URL}/repos/{owner}/{name}/contents/{path}",
                    headers=self._headers(token),
                    json={
                        "message": message,
                        "sha": sha,
                        "branch": branch,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "path": path,
                    "deleted": True,
                    "commit_sha": data["commit"]["sha"],
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return {"error": "File not found"}
                return {"error": f"GitHub API error: {e.response.status_code}"}

    async def fetch_module_files(
        self, token: str, owner: str, name: str, branch: str = "main"
    ) -> list[ModuleFileInfo]:
        """Scan workflows/, agents/, resources/ and fetch all YAML files.

        Reuses a single HTTP client for all requests.
        Returns list of ModuleFileInfo for each found YAML.
        """
        files: list[ModuleFileInfo] = []
        directories = {
            "workflows": "workflow",
            "agents": "agent",
            "resources": "resource",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for dir_name, file_type in directories.items():
                entries = await self.list_directory(
                    token, owner, name, dir_name, branch, _client=client
                )
                for entry in entries:
                    if entry["type"] != "file":
                        continue
                    if not entry["name"].endswith((".yaml", ".yml")):
                        continue
                    result = await self.get_file_content(
                        token, owner, name, entry["path"], branch, _client=client
                    )
                    if result:
                        content, sha = result
                        files.append(ModuleFileInfo(
                            file_type=file_type,
                            file_path=entry["path"],
                            content=content,
                            sha=sha,
                        ))
                        logger.info(
                            "github.file_fetched",
                            owner=owner, name=name,
                            path=entry["path"], file_type=file_type,
                        )

        return files
