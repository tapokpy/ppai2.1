import asyncio
import base64

import httpx


class GitHubPlanningError(Exception):
    """Raised when the GitHub Contents API can't be reached or rejects the
    write. Covers auth failures, network errors, and non-2xx responses —
    callers should treat this as "can't save to GitHub right now" rather
    than a bug, mirroring CloudUnavailableError in app/services/cloud_llm.py.
    """


class GitHubPlanningClient:
    def __init__(self, token: str, repo: str, file_path: str, branch: str):
        self._repo = repo
        self._file_path = file_path
        self._branch = branch
        # Serializes GET-sha -> PUT so two near-simultaneous todo entries
        # can't race on a stale sha and have the second PUT rejected.
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=15.0,
        )

    async def append_todo_entry(self, entry_markdown: str, commit_message: str) -> str:
        """Append a markdown entry to the planning file and commit it directly
        to the configured branch. Returns the new commit sha."""
        async with self._lock:
            try:
                existing_content, sha = await self._get_current_file()
                new_content = self._append_entry(existing_content, entry_markdown)
                return await self._put_file(new_content, commit_message, sha)
            except httpx.HTTPError as exc:
                raise GitHubPlanningError(str(exc)) from exc

    async def _get_current_file(self) -> tuple[str, str | None]:
        response = await self._client.get(
            f"/repos/{self._repo}/contents/{self._file_path}",
            params={"ref": self._branch},
        )
        if response.status_code == 404:
            return "# Planning\n\n", None
        response.raise_for_status()
        data = response.json()
        return base64.b64decode(data["content"]).decode("utf-8"), data["sha"]

    @staticmethod
    def _append_entry(existing_content: str, entry_markdown: str) -> str:
        separator = "" if existing_content.endswith("\n") else "\n"
        return f"{existing_content}{separator}{entry_markdown}\n"

    async def _put_file(self, content: str, commit_message: str, sha: str | None) -> str:
        payload: dict[str, str] = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self._branch,
        }
        if sha:
            payload["sha"] = sha

        response = await self._client.put(f"/repos/{self._repo}/contents/{self._file_path}", json=payload)
        response.raise_for_status()
        return response.json()["commit"]["sha"]

    async def aclose(self) -> None:
        await self._client.aclose()
