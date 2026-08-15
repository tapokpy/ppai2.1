from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.bot.filters import TODO_TRIGGER_PATTERN, ShouldRespondFilter, TodoTriggerFilter
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.bot.keyboards.reply import BTN_TODO_LIST
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.core.todo_parser import parse_todo_with_llm
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.todo import Todo
from app.models.sqlalchemy.user import User
from app.services.local_llm import LocalLLMClient

router = Router(name="todo")

TODO_LIST_EMPTY_REPLY = "Список задач пока пуст."


async def _process_and_save_todo(
    message: Message,
    raw_text: str,
    cascade_router: CascadeRouter,
    local_llm: LocalLLMClient,
    db_user: User,
) -> None:
    rag_result = cascade_router.rag_engine.query(raw_text, top_k=3)
    project_context = "\n\n".join(rag_result["documents"]) if rag_result["documents"] else ""

    parsed = await parse_todo_with_llm(raw_text, local_llm, project_context=project_context)

    async with async_session_maker() as session:
        todo = Todo(title=parsed.title, description=parsed.description, author_id=db_user.id)
        session.add(todo)
        await session.flush()
        session.add(
            MessageModel(
                user_id=db_user.id,
                telegram_message_id=message.message_id,
                prompt=message.text,
                response=parsed.title,
                source="todo",
                context_used=bool(project_context),
                structured_data={"title": parsed.title, "description": parsed.description, "todo_id": todo.id},
            )
        )
        await session.commit()

    reply = f"Добавлено в план: «{parsed.title}»"
    if parsed.description:
        reply += f"\n{parsed.description}"
    await message.answer(reply)


async def _list_todos(message: Message) -> None:
    async with async_session_maker() as session:
        todos = (await session.execute(select(Todo).order_by(Todo.created_at))).scalars().all()

    if not todos:
        await message.answer(TODO_LIST_EMPTY_REPLY)
        return

    lines = [f"{'✅' if t.done else '▫️'} {i}. {t.title}" for i, t in enumerate(todos, 1)]
    await message.answer("\n".join(lines))


@router.message(F.text, TodoTriggerFilter(), ShouldRespondFilter())
async def handle_todo(
    message: Message,
    cascade_router: CascadeRouter,
    local_llm: LocalLLMClient,
    db_user: User,
) -> None:
    cleaned_text = TODO_TRIGGER_PATTERN.sub("", message.text).strip() or message.text
    await _process_and_save_todo(message, cleaned_text, cascade_router, local_llm, db_user)


@router.message(F.text == BTN_TODO_LIST, ShouldRespondFilter())
async def show_todo_list_button(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    await _list_todos(message)


@router.message(Command("todo"))
async def cmd_todo(
    message: Message,
    command: CommandObject,
    cascade_router: CascadeRouter,
    local_llm: LocalLLMClient,
    db_user: User,
) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await _list_todos(message)
        return

    await _process_and_save_todo(message, command.args, cascade_router, local_llm, db_user)
