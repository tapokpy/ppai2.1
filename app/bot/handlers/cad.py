import asyncio
from pathlib import Path

from aiogram import F, Router
from aiogram.types import FSInputFile, Message

from app.bot.filters import CAD_TRIGGER_PATTERN, CadTriggerFilter, ShouldRespondFilter
from app.core.cad_command_parser import parse_cad_command
from app.core.config import settings
from app.core.database import async_session_maker
from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.services.cad_parser import SUPPORTED_SHAPES, UnsupportedCadFormatError, generate_drawing
from app.services.local_llm import LocalLLMClient

router = Router(name="cad")

UNKNOWN_SHAPE_REPLY = (
    f"Не понял, какой чертёж нужен. Доступные формы: {', '.join(SUPPORTED_SHAPES)}. "
    "Например: «чертеж3 рамка 1000х500»."
)
MISSING_DIMENSIONS_REPLY = "Укажите ширину и высоту в миллиметрах."


@router.message(F.text, CadTriggerFilter(), ShouldRespondFilter())
async def handle_cad_command(message: Message, local_llm: LocalLLMClient) -> None:
    cleaned_text = CAD_TRIGGER_PATTERN.sub("", message.text).strip() or message.text
    request = await parse_cad_command(cleaned_text, local_llm)

    if request is None or request.shape is None or request.shape not in SUPPORTED_SHAPES:
        await message.answer(UNKNOWN_SHAPE_REPLY)
        return

    if request.width is None or request.height is None:
        await message.answer(MISSING_DIMENSIONS_REPLY)
        return

    project_name = request.project_name or f"{request.shape}_{request.width:g}x{request.height:g}"

    try:
        output_path = await asyncio.to_thread(
            generate_drawing, request.shape, request.width, request.height, Path(settings.CAD_STORAGE_PATH), project_name
        )
    except UnsupportedCadFormatError as exc:
        await message.answer(str(exc))
        return

    async with async_session_maker() as session:
        session.add(
            EngineeringDoc(
                project_name=project_name,
                file_path=str(output_path),
                doc_type="dxf",
                extracted_data=None,
                is_generated=True,
            )
        )
        await session.commit()

    await message.answer(f"Чертёж «{project_name}» готов.")
    await message.answer_document(FSInputFile(str(output_path)))
