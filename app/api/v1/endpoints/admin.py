from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.api.v1.endpoints.chat import get_cascade_router, get_current_user_id
from app.core.config import settings
from app.core.database import async_session_maker
from app.core.router import CascadeRouter
from app.models.sqlalchemy.audit_log import AuditLog
from app.models.sqlalchemy.document import Document as DocumentModel
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.rag_trace_event import RagTraceEvent
from app.models.sqlalchemy.user import User
from app.schemas.admin import (
    AnalyticsResponse,
    AuditLogListResponse,
    AuditLogSummary,
    ChunkResponse,
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentSummary,
    MessageListResponse,
    MessageSummary,
    RagTraceResponse,
    SourceCount,
    TraceEventResponse,
)

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


@router.get("/messages", response_model=MessageListResponse, dependencies=[Depends(require_admin)])
async def list_messages(limit: int = 50, offset: int = 0, source: str | None = None) -> MessageListResponse:
    async with async_session_maker() as session:
        # created_at ties are possible (Postgres now() is transaction-start
        # time, so messages inserted in the same transaction share a
        # timestamp) — id DESC breaks ties deterministically.
        query = select(MessageModel).order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
        count_query = select(func.count()).select_from(MessageModel)
        if source is not None:
            query = query.where(MessageModel.source == source)
            count_query = count_query.where(MessageModel.source == source)

        total = (await session.execute(count_query)).scalar_one()
        rows = (await session.execute(query.limit(limit).offset(offset))).scalars().all()

    return MessageListResponse(
        items=[
            MessageSummary(
                id=m.id,
                created_at=m.created_at,
                user_id=m.user_id,
                source=m.source,
                prompt=m.prompt,
                context_used=m.context_used,
            )
            for m in rows
        ],
        total=total,
    )


@router.get("/rag_trace/{message_id}", response_model=RagTraceResponse, dependencies=[Depends(require_admin)])
async def rag_trace(message_id: int) -> RagTraceResponse:
    async with async_session_maker() as session:
        message = await session.get(MessageModel, message_id)

        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

        event_rows = (
            await session.execute(
                select(RagTraceEvent)
                .where(RagTraceEvent.message_id == message_id)
                .order_by(RagTraceEvent.seq)
            )
        ).scalars().all()

    return RagTraceResponse(
        message_id=message.id,
        source=message.source,
        prompt=message.prompt,
        rag_debug=message.rag_debug,
        rag_trace_id=message.rag_trace_id,
        timing=message.timing,
        events=[
            TraceEventResponse(
                seq=e.seq, event_name=e.event_name, payload=e.payload, created_at=e.created_at
            )
            for e in event_rows
        ],
    )


@router.get("/documents", response_model=DocumentListResponse, dependencies=[Depends(require_admin)])
async def list_documents(source: str | None = None, q: str | None = None) -> DocumentListResponse:
    async with async_session_maker() as session:
        query = select(DocumentModel).order_by(DocumentModel.created_at.desc(), DocumentModel.id.desc())
        count_query = select(func.count()).select_from(DocumentModel)
        if source is not None:
            query = query.where(DocumentModel.source == source)
            count_query = count_query.where(DocumentModel.source == source)
        if q is not None:
            query = query.where(DocumentModel.filename.ilike(f"%{q}%"))
            count_query = count_query.where(DocumentModel.filename.ilike(f"%{q}%"))

        total = (await session.execute(count_query)).scalar_one()
        rows = (await session.execute(query)).scalars().all()

    return DocumentListResponse(
        items=[
            DocumentSummary(
                id=d.id,
                source=d.source,
                filename=d.filename,
                chunk_count=d.chunk_count,
                status=d.status,
                created_at=d.created_at,
            )
            for d in rows
        ],
        total=total,
    )


@router.get("/audit", response_model=AuditLogListResponse, dependencies=[Depends(require_admin)])
async def list_audit_log(
    limit: int = 50, offset: int = 0, module: str | None = None, status_filter: str | None = None
) -> AuditLogListResponse:
    async with async_session_maker() as session:
        query = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        count_query = select(func.count()).select_from(AuditLog)
        if module is not None:
            query = query.where(AuditLog.module == module)
            count_query = count_query.where(AuditLog.module == module)
        if status_filter is not None:
            query = query.where(AuditLog.status == status_filter)
            count_query = count_query.where(AuditLog.status == status_filter)

        total = (await session.execute(count_query)).scalar_one()
        rows = (await session.execute(query.limit(limit).offset(offset))).scalars().all()

    return AuditLogListResponse(
        items=[
            AuditLogSummary(
                id=a.id,
                created_at=a.created_at,
                user_id=a.user_id,
                module=a.module,
                decision=a.decision,
                status=a.status,
                command_text=a.command_text,
                detail=a.detail,
            )
            for a in rows
        ],
        total=total,
    )


@router.get(
    "/documents/{document_id}", response_model=DocumentDetailResponse, dependencies=[Depends(require_admin)]
)
async def document_detail(
    document_id: int, cascade_router: CascadeRouter = Depends(get_cascade_router)
) -> DocumentDetailResponse:
    async with async_session_maker() as session:
        document = await session.get(DocumentModel, document_id)

    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = cascade_router.rag_engine.get_document_chunks(document.source, document.filename)

    return DocumentDetailResponse(
        document=DocumentSummary(
            id=document.id,
            source=document.source,
            filename=document.filename,
            chunk_count=document.chunk_count,
            status=document.status,
            created_at=document.created_at,
        ),
        embedding_model=document.embedding_model,
        collection=cascade_router.rag_engine.collection_name,
        chunks=[
            ChunkResponse(chunk_id=chunk_id, text=text, metadata=metadata)
            for chunk_id, text, metadata in zip(chunks["ids"], chunks["documents"], chunks["metadatas"])
        ],
    )
