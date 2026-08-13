from unittest.mock import MagicMock

from app.services.engineering_rag_ingest import (
    ENGINEERING_DOC_SOURCE,
    SHOWROOM_MEDIA_SOURCE,
    index_engineering_doc,
    index_showroom_media,
)


def test_index_engineering_doc_includes_dimensions_and_texts():
    doc = MagicMock(
        id=5,
        project_name="frame_1000x500",
        doc_type="dxf",
        is_generated=True,
        extracted_data={"dimensions": ["1000 x 500"], "texts": ["ГОСТ 123"]},
    )
    rag_engine = MagicMock()

    index_engineering_doc(rag_engine, doc)

    rag_engine.upsert_documents.assert_called_once()
    call = rag_engine.upsert_documents.call_args.kwargs
    assert "frame_1000x500" in call["texts"][0]
    assert "1000 x 500" in call["texts"][0]
    assert "ГОСТ 123" in call["texts"][0]
    assert call["ids"] == [f"{ENGINEERING_DOC_SOURCE}:5"]
    assert call["metadatas"][0] == {"source": ENGINEERING_DOC_SOURCE, "doc_id": 5, "project_name": "frame_1000x500"}


def test_index_engineering_doc_handles_missing_extracted_data():
    doc = MagicMock(id=6, project_name="plate", doc_type="dxf", is_generated=True, extracted_data=None)
    rag_engine = MagicMock()

    index_engineering_doc(rag_engine, doc)

    rag_engine.upsert_documents.assert_called_once()


def test_index_showroom_media_builds_expected_metadata():
    media = MagicMock(id=9, title="Крутое видео")
    rag_engine = MagicMock()

    index_showroom_media(rag_engine, media)

    call = rag_engine.upsert_documents.call_args.kwargs
    assert "Крутое видео" in call["texts"][0]
    assert call["ids"] == [f"{SHOWROOM_MEDIA_SOURCE}:9"]
    assert call["metadatas"][0] == {"source": SHOWROOM_MEDIA_SOURCE, "media_id": 9, "title": "Крутое видео"}
