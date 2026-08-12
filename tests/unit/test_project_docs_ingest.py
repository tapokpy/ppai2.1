from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.project_docs_ingest import PROJECT_DOC_FILENAMES, sync_project_docs


def _mock_session_maker(existing_document=None):
    """Fakes async_session_maker() so these stay fast unit tests instead of
    needing a real Postgres — mirrors the shape session.execute(...).scalar_one_or_none()
    is used for in _upsert_document_record."""
    session = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing_document
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    @asynccontextmanager
    async def session_maker():
        yield session

    return session_maker, session


@pytest.mark.asyncio
async def test_syncs_all_present_docs(tmp_path):
    for filename in PROJECT_DOC_FILENAMES:
        (tmp_path / filename).write_text(f"# {filename}\n\nSome content about the project.", encoding="utf-8")

    rag_engine = MagicMock()
    rag_engine.embedding_model_name = "all-MiniLM-L6-v2"
    session_maker, session = _mock_session_maker()

    with patch("app.services.project_docs_ingest.async_session_maker", session_maker):
        total = await sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == len(PROJECT_DOC_FILENAMES)
    assert rag_engine.upsert_documents.call_count == len(PROJECT_DOC_FILENAMES)

    first_call_kwargs = rag_engine.upsert_documents.call_args_list[0].kwargs
    assert first_call_kwargs["ids"] == [f"project_doc:{PROJECT_DOC_FILENAMES[0]}:0"]
    assert first_call_kwargs["metadatas"] == [
        {"source": "project_docs", "filename": PROJECT_DOC_FILENAMES[0], "chunk_index": 0}
    ]
    # One Document row inserted per ingested file, since none existed yet.
    assert session.add.call_count == len(PROJECT_DOC_FILENAMES)
    assert session.commit.await_count == len(PROJECT_DOC_FILENAMES)


@pytest.mark.asyncio
async def test_skips_missing_files_without_raising(tmp_path):
    (tmp_path / PROJECT_DOC_FILENAMES[0]).write_text("content", encoding="utf-8")

    rag_engine = MagicMock()
    session_maker, _ = _mock_session_maker()

    with patch("app.services.project_docs_ingest.async_session_maker", session_maker):
        total = await sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == 1
    rag_engine.upsert_documents.assert_called_once()


@pytest.mark.asyncio
async def test_empty_docs_dir_ingests_nothing(tmp_path):
    rag_engine = MagicMock()
    session_maker, session = _mock_session_maker()

    with patch("app.services.project_docs_ingest.async_session_maker", session_maker):
        total = await sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == 0
    rag_engine.upsert_documents.assert_not_called()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_calling_twice_uses_same_deterministic_ids(tmp_path):
    (tmp_path / PROJECT_DOC_FILENAMES[0]).write_text("unchanged content", encoding="utf-8")
    rag_engine = MagicMock()
    session_maker, _ = _mock_session_maker()

    with patch("app.services.project_docs_ingest.async_session_maker", session_maker):
        await sync_project_docs(rag_engine, docs_dir=tmp_path)
        await sync_project_docs(rag_engine, docs_dir=tmp_path)

    first_ids = rag_engine.upsert_documents.call_args_list[0].kwargs["ids"]
    second_ids = rag_engine.upsert_documents.call_args_list[1].kwargs["ids"]
    assert first_ids == second_ids


@pytest.mark.asyncio
async def test_updates_existing_document_record_instead_of_duplicating(tmp_path):
    (tmp_path / PROJECT_DOC_FILENAMES[0]).write_text("some updated content here", encoding="utf-8")

    rag_engine = MagicMock()
    existing_document = MagicMock()
    session_maker, session = _mock_session_maker(existing_document=existing_document)

    with patch("app.services.project_docs_ingest.async_session_maker", session_maker):
        await sync_project_docs(rag_engine, docs_dir=tmp_path)

    # An existing row is updated in place, not re-inserted.
    session.add.assert_not_called()
    assert existing_document.chunk_count > 0
    assert existing_document.char_count == len("some updated content here")
