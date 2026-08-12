import asyncio
import base64
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.github_planning import GitHubPlanningClient, GitHubPlanningError


def _client() -> GitHubPlanningClient:
    return GitHubPlanningClient(
        token="test-token", repo="tapokpy/ppai", file_path="PLANNING.md", branch="main"
    )


def _response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/repos/tapokpy/ppai/contents/PLANNING.md")
    return httpx.Response(status_code=status_code, json=json_body, request=request)


@pytest.mark.asyncio
async def test_appends_entry_to_existing_file():
    client = _client()
    existing_content = base64.b64encode("# Planning\n\n- [ ] Старая задача\n".encode()).decode()
    get_response = _response(200, {"content": existing_content, "sha": "abc123"})
    put_response = _response(200, {"commit": {"sha": "def456"}})

    client._client.get = AsyncMock(return_value=get_response)
    client._client.put = AsyncMock(return_value=put_response)

    commit_sha = await client.append_todo_entry(
        entry_markdown="- [ ] Новая задача", commit_message="Add todo: Новая задача"
    )

    assert commit_sha == "def456"
    put_kwargs = client._client.put.call_args.kwargs
    put_body = base64.b64decode(put_kwargs["json"]["content"]).decode()
    assert "- [ ] Старая задача" in put_body
    assert "- [ ] Новая задача" in put_body
    assert put_kwargs["json"]["sha"] == "abc123"
    assert put_kwargs["json"]["branch"] == "main"


@pytest.mark.asyncio
async def test_creates_file_when_missing():
    client = _client()
    client._client.get = AsyncMock(return_value=_response(404))
    put_response = _response(200, {"commit": {"sha": "new-sha"}})
    client._client.put = AsyncMock(return_value=put_response)

    await client.append_todo_entry(entry_markdown="- [ ] Первая задача", commit_message="Add todo")

    put_kwargs = client._client.put.call_args.kwargs
    assert "sha" not in put_kwargs["json"]
    put_body = base64.b64decode(put_kwargs["json"]["content"]).decode()
    assert "- [ ] Первая задача" in put_body


@pytest.mark.asyncio
async def test_raises_planning_error_on_get_failure():
    client = _client()
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(GitHubPlanningError):
        await client.append_todo_entry(entry_markdown="- [ ] Задача", commit_message="msg")


@pytest.mark.asyncio
async def test_raises_planning_error_on_put_failure():
    client = _client()
    client._client.get = AsyncMock(return_value=_response(404))
    client._client.put = AsyncMock(
        return_value=_response(422, {"message": "Invalid request"})
    )

    with pytest.raises(GitHubPlanningError):
        await client.append_todo_entry(entry_markdown="- [ ] Задача", commit_message="msg")


@pytest.mark.asyncio
async def test_concurrent_calls_are_serialized():
    client = _client()
    call_order: list[str] = []

    async def fake_get(*args, **kwargs):
        call_order.append("get")
        await asyncio.sleep(0.01)
        return _response(404)

    async def fake_put(*args, **kwargs):
        call_order.append("put")
        return _response(200, {"commit": {"sha": "sha-1"}})

    client._client.get = fake_get
    client._client.put = fake_put

    await asyncio.gather(
        client.append_todo_entry(entry_markdown="- [ ] A", commit_message="a"),
        client.append_todo_entry(entry_markdown="- [ ] B", commit_message="b"),
    )

    assert call_order == ["get", "put", "get", "put"]
