from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.v1.endpoints.chat import get_current_user_id
from app.core.config import settings
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.user import User
from app.schemas.admin import AnalyticsResponse, RagTraceResponse, SourceCount

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(user_id: int = Depends(get_current_user_id)) -> User:
    async with async_session_maker() as session:
        user = await session.get(User, user_id)

    if user is None or user.telegram_id not in settings.admin_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return user


@router.get("/analytics", response_model=AnalyticsResponse, dependencies=[Depends(require_admin)])
async def analytics() -> AnalyticsResponse:
    async with async_session_maker() as session:
        total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        approved_users = (
            await session.execute(select(func.count()).select_from(User).where(User.is_approved.is_(True)))
        ).scalar_one()
        total_messages = (await session.execute(select(func.count()).select_from(MessageModel))).scalar_one()
        by_source_rows = (
            await session.execute(select(MessageModel.source, func.count()).group_by(MessageModel.source))
        ).all()

    return AnalyticsResponse(
        total_users=total_users,
        approved_users=approved_users,
        total_messages=total_messages,
        messages_by_source=[SourceCount(source=source, count=count) for source, count in by_source_rows],
    )


@router.get("/rag_trace/{message_id}", response_model=RagTraceResponse, dependencies=[Depends(require_admin)])
async def rag_trace(message_id: int) -> RagTraceResponse:
    async with async_session_maker() as session:
        message = await session.get(MessageModel, message_id)

    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    return RagTraceResponse(
        message_id=message.id,
        source=message.source,
        prompt=message.prompt,
        rag_debug=message.rag_debug,
    )
