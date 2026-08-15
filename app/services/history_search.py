from sqlalchemy import or_, select

from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel

DEFAULT_RESULT_LIMIT = 10


async def search_messages(user_id: int, query: str, limit: int = DEFAULT_RESULT_LIMIT) -> list[MessageModel]:
    """This user's own past prompts/responses matching `query` — a
    personal-memory search ("what did I already ask/get told about X"), not
    a knowledge-base/RAG search. Scoped to user_id for the same reason
    CascadeRouter._load_recent_history is: the messages table has no
    chat_id, so there's no narrower scope available. Shared by /find
    (app/bot/handlers/rag_memory.py) and the find_history tool
    (app/services/tools/find_history_tool.py) so both behave identically."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(MessageModel)
            .where(
                MessageModel.user_id == user_id,
                or_(MessageModel.prompt.ilike(f"%{query}%"), MessageModel.response.ilike(f"%{query}%")),
            )
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
