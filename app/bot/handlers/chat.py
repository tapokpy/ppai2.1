from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import select

from app.bot.filters import ShouldRespondFilter
from app.bot.keyboards.inline import response_actions
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.doc_generator import generate_docx, generate_xlsx

router = Router(name="chat")


@router.message(F.text, ShouldRespondFilter())
async def handle_text(message: Message, cascade_router: CascadeRouter, db_user: User) -> None:
    result = await cascade_router.process_query(user_id=db_user.id, prompt=message.text)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=db_user.id,
                telegram_message_id=message.message_id,
                prompt=message.text,
                response=result["text"],
                source=result["source"],
                context_used=result["context_used"],
            )
        )
        # Group messages are already logged for every message (mentioned or not)
        # by GroupActivityMiddleware; avoid double-logging this one.
        if message.chat.type == "private":
            session.add(
                ActivityLog(
                    user_id=db_user.id,
                    chat_id=message.chat.id,
                    message_type="text",
                    summary=message.text[:200],
                )
            )
        await session.commit()

    await message.answer(result["text"], reply_markup=response_actions(message.message_id))


async def _get_stored_message(user_id: int, telegram_message_id: int) -> MessageModel | None:
    async with async_session_maker() as session:
        result = await session.execute(
            select(MessageModel).where(
                MessageModel.user_id == user_id,
                MessageModel.telegram_message_id == telegram_message_id,
            )
        )
        return result.scalar_one_or_none()


@router.callback_query(F.data.startswith("export_docx:"))
async def export_docx_callback(callback: CallbackQuery, db_user: User) -> None:
    telegram_message_id = int(callback.data.split(":", 1)[1])
    stored_message = await _get_stored_message(db_user.id, telegram_message_id)

    if stored_message is None:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    file_path = generate_docx(
        {
            "title": "Коммерческое предложение",
            "items": [{"name": stored_message.prompt, "quantity": 1, "unit": "шт", "price": ""}],
            "notes": stored_message.response,
        }
    )

    await callback.message.answer_document(FSInputFile(file_path))
    await callback.answer()


@router.callback_query(F.data.startswith("export_xlsx:"))
async def export_xlsx_callback(callback: CallbackQuery, db_user: User) -> None:
    telegram_message_id = int(callback.data.split(":", 1)[1])
    stored_message = await _get_stored_message(db_user.id, telegram_message_id)

    if stored_message is None:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    file_path = generate_xlsx(
        {
            "title": "Смета",
            "rows": [{"name": stored_message.prompt, "quantity": 1, "unit_price": 0}],
        }
    )

    await callback.message.answer_document(FSInputFile(file_path))
    await callback.answer()


@router.callback_query(F.data.startswith("ask_cloud:"))
async def ask_cloud_callback(callback: CallbackQuery, db_user: User, cascade_router: CascadeRouter) -> None:
    telegram_message_id = int(callback.data.split(":", 1)[1])
    stored_message = await _get_stored_message(db_user.id, telegram_message_id)

    if stored_message is None:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    result = await cascade_router.process_query(
        user_id=db_user.id, prompt=stored_message.prompt, use_cloud_override=True
    )

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=db_user.id,
                telegram_message_id=callback.message.message_id,
                prompt=stored_message.prompt,
                response=result["text"],
                source=result["source"],
                context_used=result["context_used"],
            )
        )
        await session.commit()

    await callback.message.answer(result["text"], reply_markup=response_actions(callback.message.message_id))
    await callback.answer()


@router.callback_query(F.data.startswith("save_kb:"))
async def save_to_kb_callback(callback: CallbackQuery, db_user: User, cascade_router: CascadeRouter) -> None:
    telegram_message_id = int(callback.data.split(":", 1)[1])
    stored_message = await _get_stored_message(db_user.id, telegram_message_id)

    if stored_message is None:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    summary = await cascade_router.local_llm.generate(
        prompt=f"Вопрос: {stored_message.prompt}\nОтвет: {stored_message.response}",
        system_prompt="Сформируй краткую инструкцию в формате Markdown по решению этой задачи.",
    )

    cascade_router.rag_engine.add_documents(
        texts=[summary],
        metadatas=[
            {
                "source": "harvested",
                "author": str(db_user.id),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    )

    await callback.answer("Инструкция сохранена в базу знаний")
