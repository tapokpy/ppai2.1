from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards.inline import response_actions
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.activity_log import ActivityLog
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User

router = Router(name="chat")


@router.message(F.text)
async def handle_text(message: Message, cascade_router: CascadeRouter, db_user: User) -> None:
    result = await cascade_router.process_query(user_id=db_user.id, prompt=message.text)

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=db_user.id,
                prompt=message.text,
                response=result["text"],
                source=result["source"],
                context_used=result["context_used"],
            )
        )
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
