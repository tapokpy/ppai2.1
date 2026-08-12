from pathlib import Path

from loguru import logger
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.sqlalchemy.document import Document
from app.services.pdf_parser import chunk_text
from app.services.rag_engine import RAGEngine

PROJECT_DOCS_SOURCE = "project_docs"
# This file lives at app/services/project_docs_ingest.py, so parents[2] is
# the repo root — both locally (C:\ppai) and inside the bot container
# (WORKDIR /app, where Dockerfile.bot COPYs the root *.md files alongside
# the app/ directory).
PROJECT_DOCS_DIR = Path(__file__).resolve().parents[2]
PROJECT_DOC_FILENAMES = [
    "ARCHITECTURE.md",
    "README.md",
    "AUTONOMOUS_EXECUTION.md",
    "DEVELOPMENT_TOOLS.md",
    "OPEN_SOURCE_STRATEGY.md",
    "INSTALL.md",
    "DEPLOYMENT.md",
]


async def _upsert_document_record(
    filename: str, chunk_count: int, char_count: int, embedding_model: str
) -> None:
    """Keeps the `documents` table (provenance index for the RAG
    visualization admin panel) in sync with what was just upserted into
    Chroma. No unique DB constraint on (source, filename) — idempotent
    re-ingestion is handled here via a query-then-update-or-insert, matching
    the same "no delete-if-missing" tolerance as the Chroma upsert above."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Document).where(Document.source == PROJECT_DOCS_SOURCE, Document.filename == filename)
        )
        document = result.scalar_one_or_none()

        if document is None:
            session.add(
                Document(
                    source=PROJECT_DOCS_SOURCE,
                    filename=filename,
                    chunk_count=chunk_count,
                    char_count=char_count,
                    embedding_model=embedding_model,
                )
            )
        else:
            document.chunk_count = chunk_count
            document.char_count = char_count
            document.embedding_model = embedding_model

        await session.commit()


async def sync_project_docs(rag_engine: RAGEngine, docs_dir: Path = PROJECT_DOCS_DIR) -> int:
    """Ingest the project's own root *.md docs into RAG so chat and the todo
    parser are grounded in the real architecture/feature set.

    Idempotent: ids are deterministic (f"project_doc:{filename}:{i}"), so
    calling this repeatedly (e.g. on every bot startup) upserts the same
    entries instead of accumulating duplicates. Known limitation: if a doc
    shrinks to fewer chunks than a previous run produced, the old trailing
    chunk ids are not deleted (upsert has no delete-if-missing semantics) —
    acceptable for docs that are edited rarely; not worth solving now.
    """
    total_chunks = 0
    for filename in PROJECT_DOC_FILENAMES:
        path = docs_dir / filename
        if not path.exists():
            logger.warning(f"Project doc {filename} not found at {path}, skipping RAG ingestion")
            continue

        text = path.read_text(encoding="utf-8")
        chunks = chunk_text(text)
        if not chunks:
            continue

        ids = [f"project_doc:{filename}:{i}" for i in range(len(chunks))]
        metadatas = [
            {"source": PROJECT_DOCS_SOURCE, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        rag_engine.upsert_documents(texts=chunks, metadatas=metadatas, ids=ids)
        await _upsert_document_record(
            filename=filename,
            chunk_count=len(chunks),
            char_count=len(text),
            embedding_model=rag_engine.embedding_model_name,
        )
        total_chunks += len(chunks)

    logger.info(f"Ingested {total_chunks} project doc chunks into RAG")
    return total_chunks
