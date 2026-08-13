import asyncio
import csv
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.types import FSInputFile, Message
from loguru import logger

from app.bot.filters import ShouldRespondFilter
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.document import Document
from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.models.sqlalchemy.user import User
from app.services import cad_parser
from app.services.engineering_rag_ingest import index_engineering_doc
from app.services.pdf_parser import chunk_text, extract_text
from app.services.stock_import import StockTableError, parse_stock_table, upsert_stock_rows

router = Router(name="documents")

DOCUMENT_TEMP_DIR = Path("data/temp")
CAD_EXTENSIONS = {".dxf", ".dwg", ".cdr"}
STOCK_TABLE_EXTENSIONS = {".xlsx", ".csv"}


def _is_pdf(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type == "application/pdf":
        return True
    return bool(file_name) and file_name.lower().endswith(".pdf")


def _cad_extension(file_name: str | None) -> str | None:
    if not file_name:
        return None
    ext = Path(file_name).suffix.lower()
    return ext if ext in CAD_EXTENSIONS else None


def _stock_table_extension(file_name: str | None) -> str | None:
    if not file_name:
        return None
    ext = Path(file_name).suffix.lower()
    return ext if ext in STOCK_TABLE_EXTENSIONS else None


@router.message(F.document, ShouldRespondFilter())
async def handle_document(message: Message, bot: Bot, cascade_router: CascadeRouter, db_user: User) -> None:
    document = message.document

    if _is_pdf(document.file_name, document.mime_type):
        await _handle_pdf_upload(message, bot, cascade_router, db_user)
        return

    cad_ext = _cad_extension(document.file_name)
    if cad_ext:
        await _handle_cad_upload(message, bot, cad_ext, cascade_router)
        return

    stock_ext = _stock_table_extension(document.file_name)
    if stock_ext:
        await _handle_stock_table_upload(message, bot, stock_ext)
        return

    await message.answer(
        "Пока поддерживается загрузка PDF, .dxf, .dwg, .xlsx/.csv (остатки склада) — "
        ".cdr не читается ни одним инструментом."
    )


async def _handle_pdf_upload(message: Message, bot: Bot, cascade_router: CascadeRouter, db_user: User) -> None:
    document = message.document
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


def _format_cad_summary(project_name: str, extracted: cad_parser.ExtractedCadData) -> str:
    lines = [f"Чертёж «{project_name}» разобран."]
    if extracted.entity_counts:
        counts = ", ".join(f"{name}: {count}" for name, count in extracted.entity_counts.items())
        lines.append(f"Элементы: {counts}")
    if extracted.dimensions:
        lines.append(f"Размеры: {', '.join(extracted.dimensions[:10])}")
    if extracted.texts:
        lines.append(f"Текст на чертеже: {', '.join(extracted.texts[:10])}")
    return "\n".join(lines)


async def _handle_cad_upload(message: Message, bot: Bot, ext: str, cascade_router: CascadeRouter) -> None:
    document = message.document
    file = await bot.get_file(document.file_id)
    DOCUMENT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = DOCUMENT_TEMP_DIR / f"cad_{uuid4().hex}{ext}"

    try:
        await bot.download_file(file.file_path, destination=local_path)

        try:
            doc, doc_type = await asyncio.to_thread(
                cad_parser.open_drawing, local_path, settings.ODA_FILE_CONVERTER_PATH
            )
        except (cad_parser.UnsupportedCadFormatError, cad_parser.CadConversionError, cad_parser.CadParseError) as exc:
            logger.warning(f"CAD upload failed for {document.file_name}: {exc}")
            await message.answer(str(exc))
            return

        extracted = await asyncio.to_thread(cad_parser.extract_data, doc)

        cad_storage = Path(settings.CAD_STORAGE_PATH)
        cad_storage.mkdir(parents=True, exist_ok=True)
        stored_dxf = cad_storage / f"{uuid4().hex}.dxf"
        doc.saveas(str(stored_dxf))
        rendered_pdf = stored_dxf.with_suffix(".pdf")
        await asyncio.to_thread(cad_parser.render_to_pdf, doc, rendered_pdf)
    finally:
        local_path.unlink(missing_ok=True)

    project_name = Path(document.file_name).stem

    async with async_session_maker() as session:
        doc = EngineeringDoc(
            project_name=project_name,
            file_path=str(stored_dxf),
            doc_type=doc_type,
            extracted_data=extracted.to_dict(),
            is_generated=False,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        index_engineering_doc(cascade_router.rag_engine, doc)

    await message.answer(_format_cad_summary(project_name, extracted))
    await message.answer_document(FSInputFile(str(rendered_pdf)))


def _read_xlsx_rows(path: Path) -> list[list[str]]:
    # Imported lazily — openpyxl is only needed for this one upload path.
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    return [["" if cell is None else str(cell) for cell in row] for row in sheet.iter_rows(values_only=True)]


def _read_csv_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


async def _handle_stock_table_upload(message: Message, bot: Bot, ext: str) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    document = message.document
    file = await bot.get_file(document.file_id)
    DOCUMENT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = DOCUMENT_TEMP_DIR / f"stock_{uuid4().hex}{ext}"

    try:
        await bot.download_file(file.file_path, destination=local_path)
        reader = _read_xlsx_rows if ext == ".xlsx" else _read_csv_rows
        rows = await asyncio.to_thread(reader, local_path)
    finally:
        local_path.unlink(missing_ok=True)

    try:
        stock_rows = parse_stock_table(rows)
    except StockTableError as exc:
        await message.answer(str(exc))
        return

    async with async_session_maker() as session:
        count = await upsert_stock_rows(session, stock_rows)

    await message.answer(f"Импортировано позиций: {count}.")
