import asyncio
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.types import Message

from app.bot.filters import ShouldRespondFilter
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.document import Document
from app.models.sqlalchemy.user import User
from app.services.pdf_parser import chunk_text, extract_text

router = Router(name="documents")

DOCUMENT_TEMP_DIR = Path("data/temp")


def _is_pdf(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type == "application/pdf":
        return True
    return bool(file_name) and file_name.lower().endswith(".pdf")


@router.message(F.document, ShouldRespondFilter())
async def handle_document(message: Message, bot: Bot, cascade_router: CascadeRouter, db_user: User) -> None:
    document = message.document

    if not _is_pdf(document.file_name, document.mime_type):
        await message.answer("Пока поддерживается загрузка только PDF-файлов.")
        return

    file = await bot.get_file(document.file_id)
    DOCUMENT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = DOCUMENT_TEMP_DIR / f"doc_{uuid4().hex}.pdf"

    try:
        await bot.download_file(file.file_path, destination=local_path)
        text = await asyncio.to_thread(extract_text, str(local_path))
    finally:
        local_path.unlink(missing_ok=True)

    chunks = chunk_text(text)
    if not chunks:
        await message.answer("Не удалось извлечь текст из документа.")
        return

    filename = document.file_name or "document.pdf"
    cascade_router.rag_engine.add_documents(
        texts=chunks,
        metadatas=[{"source": "pdf_upload", "filename": filename, "uploaded_by": str(db_user.id)} for _ in chunks],
    )

    async with async_session_maker() as session:
        session.add(
            Document(
                source="pdf_upload",
                filename=filename,
                uploaded_by=db_user.id,
                chunk_count=len(chunks),
                char_count=len(text),
                embedding_model=cascade_router.rag_engine.embedding_model_name,
            )
        )
        await session.commit()

    await message.answer(f"Документ «{filename}» обработан и добавлен в базу знаний ({len(chunks)} фрагм.).")
