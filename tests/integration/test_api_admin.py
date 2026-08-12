from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.core.database import async_session_maker
from app.core.security import create_access_token
from app.main import app
from app.models.sqlalchemy.document import Document as DocumentModel
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.rag_trace_event import RagTraceEvent
from app.models.sqlalchemy.user import User
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.fixture(autouse=True)
def _default_cascade_router_state():
    # app.state.cascade_router is normally populated by the app's lifespan
    # handler, which the ASGITransport client below does not trigger.
    app.state.cascade_router = MagicMock()
    yield


async def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _seed_user(telegram_id: int, is_approved: bool = True) -> User:
    async with async_session_maker() as session:
        user = User(telegram_id=telegram_id, username="u", is_approved=is_approved)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_analytics_requires_admin(clean_db):
    user = await _seed_user(1)
    token = create_access_token(user_id=user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [999]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_analytics_returns_aggregates_for_admin(clean_db):
    admin_user = await _seed_user(2)
    other_user = await _seed_user(3)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=other_user.id,
                telegram_message_id=None,
                prompt="p",
                response="r",
                source="local",
                context_used=False,
            )
        )
        session.add(
            MessageModel(
                user_id=other_user.id,
                telegram_message_id=None,
                prompt="p2",
                response="r2",
                source="rag",
                context_used=True,
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [2]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total_users"] == 2
    assert body["approved_users"] == 2
    assert body["total_messages"] == 2
    assert {row["source"]: row["count"] for row in body["messages_by_source"]} == {"local": 1, "rag": 1}


@pytest.mark.asyncio
async def test_rag_trace_returns_debug_payload(clean_db):
    admin_user = await _seed_user(4)
    other_user = await _seed_user(5)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        message = MessageModel(
            user_id=other_user.id,
            telegram_message_id=None,
            prompt="Какой шаг пикселя?",
            response="P2.5",
            source="rag",
            context_used=True,
            rag_debug={"max_score": 0.91, "retrieved": [{"snippet": "P2.5 модуль", "score": 0.91, "metadata": {}}]},
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        message_id = message.id

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [4]
        async with await _client() as client:
            response = await client.get(
                f"/api/v1/admin/rag_trace/{message_id}", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "rag"
    assert body["rag_debug"]["max_score"] == 0.91


@pytest.mark.asyncio
async def test_rag_trace_404_for_unknown_message(clean_db):
    admin_user = await _seed_user(6)
    token = create_access_token(user_id=admin_user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [6]
        async with await _client() as client:
            response = await client.get(
                "/api/v1/admin/rag_trace/999999", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_rag_trace_includes_timing_and_ordered_events(clean_db):
    admin_user = await _seed_user(7)
    other_user = await _seed_user(8)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        message = MessageModel(
            user_id=other_user.id,
            telegram_message_id=None,
            prompt="вопрос",
            response="ответ",
            source="rag",
            context_used=True,
            timing={"rag_seconds": 0.02, "local_seconds": 1.5},
            rag_trace_id="trace-abc",
        )
        session.add(message)
        await session.flush()
        session.add_all(
            [
                RagTraceEvent(
                    trace_id="trace-abc", message_id=message.id, seq=2,
                    event_name="query_embedded", payload={"model": "m"},
                ),
                RagTraceEvent(
                    trace_id="trace-abc", message_id=message.id, seq=1,
                    event_name="retrieval_started", payload={},
                ),
            ]
        )
        await session.commit()
        message_id = message.id

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [7]
        async with await _client() as client:
            response = await client.get(
                f"/api/v1/admin/rag_trace/{message_id}", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200
    body = response.json()
    assert body["rag_trace_id"] == "trace-abc"
    assert body["timing"] == {"rag_seconds": 0.02, "local_seconds": 1.5}
    # Returned ordered by seq, not insertion order.
    assert [e["event_name"] for e in body["events"]] == ["retrieval_started", "query_embedded"]


@pytest.mark.asyncio
async def test_list_messages_requires_admin(clean_db):
    user = await _seed_user(9)
    token = create_access_token(user_id=user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [999]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/messages", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_messages_returns_recent_messages_newest_first(clean_db):
    admin_user = await _seed_user(10)
    other_user = await _seed_user(11)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=other_user.id, telegram_message_id=None, prompt="первый",
                response="r1", source="local", context_used=False,
            )
        )
        session.add(
            MessageModel(
                user_id=other_user.id, telegram_message_id=None, prompt="второй",
                response="r2", source="rag", context_used=True,
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [10]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/messages", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [m["prompt"] for m in body["items"]] == ["второй", "первый"]


@pytest.mark.asyncio
async def test_list_messages_filters_by_source(clean_db):
    admin_user = await _seed_user(12)
    other_user = await _seed_user(13)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=other_user.id, telegram_message_id=None, prompt="p1",
                response="r1", source="local", context_used=False,
            )
        )
        session.add(
            MessageModel(
                user_id=other_user.id, telegram_message_id=None, prompt="p2",
                response="r2", source="rag", context_used=True,
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [12]
        async with await _client() as client:
            response = await client.get(
                "/api/v1/admin/messages?source=rag", headers={"Authorization": f"Bearer {token}"}
            )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["prompt"] == "p2"


@pytest.mark.asyncio
async def test_list_documents_returns_seeded_documents(clean_db):
    admin_user = await _seed_user(14)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        session.add(
            DocumentModel(
                source="project_docs", filename="ARCHITECTURE.md", chunk_count=5,
                embedding_model="all-MiniLM-L6-v2",
            )
        )
        await session.commit()

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [14]
        async with await _client() as client:
            response = await client.get("/api/v1/admin/documents", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "ARCHITECTURE.md"


@pytest.mark.asyncio
async def test_document_detail_returns_live_chunks_from_rag_engine(clean_db):
    admin_user = await _seed_user(15)
    token = create_access_token(user_id=admin_user.id)

    async with async_session_maker() as session:
        document = DocumentModel(
            source="project_docs", filename="ARCHITECTURE.md", chunk_count=1,
            embedding_model="all-MiniLM-L6-v2",
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)
        document_id = document.id

    app.state.cascade_router.rag_engine.get_document_chunks.return_value = {
        "ids": ["project_doc:ARCHITECTURE.md:0"],
        "documents": ["текст чанка"],
        "metadatas": [{"source": "project_docs", "filename": "ARCHITECTURE.md", "chunk_index": 0}],
    }
    app.state.cascade_router.rag_engine.collection_name = "knowledge_base"

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [15]
        async with await _client() as client:
            response = await client.get(
                f"/api/v1/admin/documents/{document_id}", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["filename"] == "ARCHITECTURE.md"
    assert body["collection"] == "knowledge_base"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["text"] == "текст чанка"
    app.state.cascade_router.rag_engine.get_document_chunks.assert_called_once_with(
        "project_docs", "ARCHITECTURE.md"
    )


@pytest.mark.asyncio
async def test_document_detail_404_for_unknown_document(clean_db):
    admin_user = await _seed_user(16)
    token = create_access_token(user_id=admin_user.id)

    with patch("app.api.v1.endpoints.admin.settings") as settings_mock:
        settings_mock.admin_ids = [16]
        async with await _client() as client:
            response = await client.get(
                "/api/v1/admin/documents/999999", headers={"Authorization": f"Bearer {token}"}
            )

    assert response.status_code == 404
