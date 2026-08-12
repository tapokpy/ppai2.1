from unittest.mock import MagicMock

from app.services.project_docs_ingest import PROJECT_DOC_FILENAMES, sync_project_docs


def test_syncs_all_present_docs(tmp_path):
    for filename in PROJECT_DOC_FILENAMES:
        (tmp_path / filename).write_text(f"# {filename}\n\nSome content about the project.", encoding="utf-8")

    rag_engine = MagicMock()

    total = sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == len(PROJECT_DOC_FILENAMES)
    assert rag_engine.upsert_documents.call_count == len(PROJECT_DOC_FILENAMES)

    first_call_kwargs = rag_engine.upsert_documents.call_args_list[0].kwargs
    assert first_call_kwargs["ids"] == [f"project_doc:{PROJECT_DOC_FILENAMES[0]}:0"]
    assert first_call_kwargs["metadatas"] == [
        {"source": "project_docs", "filename": PROJECT_DOC_FILENAMES[0], "chunk_index": 0}
    ]


def test_skips_missing_files_without_raising(tmp_path):
    (tmp_path / PROJECT_DOC_FILENAMES[0]).write_text("content", encoding="utf-8")

    rag_engine = MagicMock()

    total = sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == 1
    rag_engine.upsert_documents.assert_called_once()


def test_empty_docs_dir_ingests_nothing(tmp_path):
    rag_engine = MagicMock()

    total = sync_project_docs(rag_engine, docs_dir=tmp_path)

    assert total == 0
    rag_engine.upsert_documents.assert_not_called()


def test_calling_twice_uses_same_deterministic_ids(tmp_path):
    (tmp_path / PROJECT_DOC_FILENAMES[0]).write_text("unchanged content", encoding="utf-8")
    rag_engine = MagicMock()

    sync_project_docs(rag_engine, docs_dir=tmp_path)
    sync_project_docs(rag_engine, docs_dir=tmp_path)

    first_ids = rag_engine.upsert_documents.call_args_list[0].kwargs["ids"]
    second_ids = rag_engine.upsert_documents.call_args_list[1].kwargs["ids"]
    assert first_ids == second_ids
