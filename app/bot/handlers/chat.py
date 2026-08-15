from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, FSInputFile, Message
from loguru import logger
from sqlalchemy import select

from app.bot.filters import ShouldRespondFilter
from app.bot.handlers.admin import is_admin
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.document import Document
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.rag_trace_event import RagTraceEvent
from app.models.sqlalchemy.user import User
from app.services.doc_generator import generate_docx, generate_xlsx
from app.services.stt import Transcriber

router = Router(name="chat")

VOICE_TEMP_DIR = Path("data/temp")

# Local inference can take anywhere from ~2s (warm GPU) to 2+ minutes (cold
# start / CPU fallback) — this gives immediate feedback that the message
# was received rather than leaving the user staring at silence, and is
# removed once the real answer is ready.
THINKING_PLACEHOLDER = "💭 Принял, думаю..."

_CONFIDENCE_EMOJI = {"high": "✅", "medium": "⚠️", "low": "❓"}


def _basic_metrics_line(result: dict) -> str:
    """Response time + confidence — shown to every user, as a footer below
    the answer (see _format_reply).

    Settled by explicit user decision in chat (confirmed twice, in writing,
    after conflicting concurrent edits from another session kept reverting
    this to admin-only): timing/confidence for everyone, extra diagnostic
    detail (source/RAG score/token cost) admin-only — see _admin_debug_line.
    """
    parts = []

    elapsed = result.get("elapsed_seconds")
    if elapsed is not None:
        parts.append(f"⏱ {elapsed}с")

    confidence = result.get("confidence")
    if confidence:
        emoji = _CONFIDENCE_EMOJI.get(confidence, "")
        parts.append(f"{emoji} {confidence}".strip())

    return " · ".join(parts)


_TIMING_LABELS = (("rag_seconds", "rag"), ("local_seconds", "llm"), ("cloud_seconds", "cloud"))


def _timing_breakdown(result: dict) -> str:
    """Per-phase breakdown of the total ⏱ shown above — answers "why did
    this take so long" (almost always: local Ollama inference is CPU-only
    and dominates every response; RAG lookup itself is near-instant)."""
    timing = result.get("timing")
    if not timing:
        return ""
    parts = [f"{label} {timing[key]}с" for key, label in _TIMING_LABELS if key in timing]
    return " + ".join(parts)


def _admin_debug_line(result: dict) -> str:
    """Extra diagnostic detail (source, per-phase timing breakdown, RAG
    score, token usage/estimated cost) appended only for admins — everyone
    else just gets the timing/confidence line above."""
    parts = [str(result.get("source", "?"))]

    timing_breakdown = _timing_breakdown(result)
    if timing_breakdown:
        parts.append(timing_breakdown)

    rag_debug = result.get("rag_debug")
    if rag_debug:
        parts.append(f"score {rag_debug['max_score']:.2f}")

    usage = result.get("llm_usage")
    if usage and usage.get("prompt_tokens") is not None:
        token_part = f"{usage['prompt_tokens']}+{usage['completion_tokens']} ток"
        if usage.get("estimated_cost_usd"):
            token_part += f" (~${usage['estimated_cost_usd']})"
        parts.append(token_part)

    return "🔧 " + " · ".join(parts)


_FOOTER_DIVIDER = "┄┄┄┄┄┄┄┄┄┄"


def _format_reply(result: dict, db_user: User) -> str:
    # Answer first, metrics as a clearly-separated footer below it — moved
    # here (was above the answer) per explicit user request in chat: a
    # metrics line ahead of the answer read as noise before the actual
    # content, a footer after it reads as a label/signature instead.
    lines = [line for line in [_basic_metrics_line(result)] if line]

    if is_admin(db_user.telegram_id):
        admin_line = _admin_debug_line(result)
        if admin_line != "🔧 ":
            lines.append(admin_line)

    if not lines:
        return result["text"]

    return f"{result['text']}\n\n{_FOOTER_DIVIDER}\n" + "\n".join(lines)


def _build_message_model(db_user: User, telegram_message_id: int, prompt: str, result: dict) -> MessageModel:
    return MessageModel(
        user_id=db_user.id,
        telegram_message_id=telegram_message_id,
        prompt=prompt,
        response=result["text"],
        source=result["source"],
        context_used=result["context_used"],
        rag_debug=result.get("rag_debug"),
        timing=result.get("timing"),
        rag_trace_id=result.get("rag_trace_id"),
        structured_data=result.get("structured_data"),
    )


async def _save_message_with_trace(session, message: MessageModel, trace_events: list[dict] | None) -> None:
    """Insert the message, then its ordered RagTraceEvent rows (needs the
    message's id, hence the flush before add_all) — one commit either way."""
    session.add(message)
    await session.flush()
    if trace_events:
        session.add_all(
            [
                RagTraceEvent(
                    trace_id=message.rag_trace_id,
                    message_id=message.id,
                    seq=event["seq"],
                    event_name=event["event_name"],
                    payload=event["payload"],
                )
                for event in trace_events
            ]
        )


async def _process_and_reply(
    message: Message,
    cascade_router: CascadeRouter,
    db_user: User,
    prompt: str,
    message_type: str = "text",
) -> None:
    placeholder = await message.answer(THINKING_PLACEHOLDER)

    result = await cascade_router.process_query(
        user_id=db_user.id, prompt=prompt, is_admin=is_admin(db_user.telegram_id)
    )

    async with async_session_maker() as session:
        db_message = _build_message_model(db_user, message.message_id, prompt, result)
        await _save_message_with_trace(session, db_message, result.get("trace_events"))
        # Group messages are already logged for every message (mentioned or not)
        # by GroupActivityMiddleware; avoid double-logging this one.
        if message.chat.type == "private":
            session.add(
                ActivityLog(
                    user_id=db_user.id,
                    chat_id=message.chat.id,
                    message_type=message_type,
                    summary=prompt[:200],
                )
            )
        await session.commit()

    try:
        await placeholder.delete()
    except Exception as exc:
        # Not fatal — e.g. the chat doesn't allow the bot to delete messages.
        # The real answer still gets sent either way.
        logger.warning(f"Failed to delete thinking placeholder: {exc}")

    await message.answer(_format_reply(result, db_user))

    attachment = result.get("tool_attachment")
    if attachment is not None:
        await message.answer_document(FSInputFile(attachment.file_path))


@router.message(F.text, ShouldRespondFilter())
async def handle_text(message: Message, cascade_router: CascadeRouter, db_user: User) -> None:
    await _process_and_reply(message, cascade_router, db_user, message.text)


@router.message(F.voice, ShouldRespondFilter())
async def handle_voice(
    message: Message, cascade_router: CascadeRouter, db_user: User, bot: Bot, transcriber: Transcriber
) -> None:
    # Transcription (CPU Whisper) can itself take a while, separately from
    # the LLM cascade afterward — without this, a voice message produced no
    # visible reaction at all until both steps finished, which read as "no
    # response" even though the bot was working the whole time.
    listening_placeholder = await message.answer("🎙 Распознаю голосовое сообщение...")

    file = await bot.get_file(message.voice.file_id)
    VOICE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    local_path = VOICE_TEMP_DIR / f"voice_{uuid4().hex}.ogg"

    try:
        await bot.download_file(file.file_path, destination=local_path)
        transcript = await transcriber.transcribe(str(local_path))
    finally:
        local_path.unlink(missing_ok=True)

    try:
        await listening_placeholder.delete()
    except Exception as exc:
        logger.warning(f"Failed to delete voice-listening placeholder: {exc}")

    if not transcript.strip():
        await message.answer("Не удалось распознать голосовое сообщение. Попробуйте ещё раз или напишите текстом.")
        return

    # Shown as its own message (not folded into the final answer) so the
    # user can tell right away whether Whisper heard them correctly, before
    # waiting on the LLM cascade for the actual answer.
    await message.answer(f"🎧 Распознано: «{transcript}»")

    await _process_and_reply(message, cascade_router, db_user, transcript, message_type="voice")


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

    structured = stored_message.structured_data
    if structured:
        proposal_data = {
            "title": structured.get("title", "Коммерческое предложение"),
            "items": structured.get("items", []),
            "notes": stored_message.response,
        }
    else:
        proposal_data = {
            "title": "Коммерческое предложение",
            "items": [{"name": stored_message.prompt, "quantity": 1, "unit": "шт", "price": ""}],
            "notes": stored_message.response,
        }

    file_path = generate_docx(proposal_data)

    await callback.message.answer_document(FSInputFile(file_path))
    await callback.answer()


@router.callback_query(F.data.startswith("export_xlsx:"))
async def export_xlsx_callback(callback: CallbackQuery, db_user: User) -> None:
    telegram_message_id = int(callback.data.split(":", 1)[1])
    stored_message = await _get_stored_message(db_user.id, telegram_message_id)

    if stored_message is None:
        await callback.answer("Сообщение не найдено", show_alert=True)
        return

    structured = stored_message.structured_data
    if structured:
        estimate_data = {
            "title": structured.get("title", "Смета"),
            "rows": structured.get("rows", []),
        }
    else:
        estimate_data = {
            "title": "Смета",
            "rows": [{"name": stored_message.prompt, "quantity": 1, "unit_price": 0}],
        }

    file_path = generate_xlsx(estimate_data)

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
        db_message = _build_message_model(db_user, callback.message.message_id, stored_message.prompt, result)
        await _save_message_with_trace(session, db_message, result.get("trace_events"))
        await session.commit()

    await callback.message.answer(_format_reply(result, db_user))
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

    async with async_session_maker() as session:
        session.add(
            Document(
                source="harvested",
                filename=None,
                uploaded_by=db_user.id,
                chunk_count=1,
                char_count=len(summary),
                embedding_model=cascade_router.rag_engine.embedding_model_name,
            )
        )
        await session.commit()

    await callback.answer("Инструкция сохранена в базу знаний")
