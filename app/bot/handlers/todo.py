from aiogram import F, Router
from aiogram.types import Message
from loguru import logger

from app.bot.filters import TODO_TRIGGER_PATTERN, ShouldRespondFilter, TodoTriggerFilter
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.core.todo_parser import parse_todo_with_llm
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.services.github_planning import GitHubPlanningClient, GitHubPlanningError
from app.services.local_llm import LocalLLMClient

router = Router(name="todo")

GITHUB_UNAVAILABLE_REPLY = (
    "Не получилось сохранить задачу в PLANNING.md на GitHub — попробуйте ещё раз чуть позже. "
    "Сама задача сохранена в истории диалога."
)


def _format_entry_markdown(title: str, description: str | None, author: str) -> str:
    line = f"- [ ] {title} (via @{author})"
    if description:
        line += f"\n  {description}"
    return line


@router.message(F.text, TodoTriggerFilter(), ShouldRespondFilter())
async def handle_todo(
    message: Message,
    cascade_router: CascadeRouter,
    local_llm: LocalLLMClient,
    github_planning_client: GitHubPlanningClient,
    db_user: User,
) -> None:
    cleaned_text = TODO_TRIGGER_PATTERN.sub("", message.text).strip() or message.text

    rag_result = cascade_router.rag_engine.query(cleaned_text, top_k=3)
    project_context = "\n\n".join(rag_result["documents"]) if rag_result["documents"] else ""

    parsed = await parse_todo_with_llm(cleaned_text, local_llm, project_context=project_context)

    author = db_user.username or str(db_user.telegram_id)
    entry_markdown = _format_entry_markdown(parsed.title, parsed.description, author)

    github_synced = True
    try:
        await github_planning_client.append_todo_entry(
            entry_markdown=entry_markdown,
            commit_message=f"Add todo via bot: {parsed.title}",
        )
    except GitHubPlanningError as exc:
        logger.warning(f"Failed to write todo to GitHub PLANNING.md: {exc}")
        github_synced = False

    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=db_user.id,
                telegram_message_id=message.message_id,
                prompt=message.text,
                response=entry_markdown,
                source="todo",
                context_used=bool(project_context),
                structured_data={
                    "title": parsed.title,
                    "description": parsed.description,
                    "github_synced": github_synced,
                },
            )
        )
        await session.commit()

    if not github_synced:
        await message.answer(GITHUB_UNAVAILABLE_REPLY)
        return

    reply = f"Добавлено в план: «{parsed.title}»"
    if parsed.description:
        reply += f"\n{parsed.description}"
    await message.answer(reply)
