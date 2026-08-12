from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import async_session_maker
from app.core.observability import get_tracer
from app.core.router import CascadeRouter
from app.core.security import TokenError, decode_access_token
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.rag_trace_event import RagTraceEvent
from app.schemas.chat import ChatChoice, ChatMessage, ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])
security = HTTPBearer()


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    try:
        return decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_cascade_router(request: Request) -> CascadeRouter:
    return request.app.state.cascade_router


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user_id: int = Depends(get_current_user_id),
    cascade_router: CascadeRouter = Depends(get_cascade_router),
) -> ChatResponse:
    trace = get_tracer().trace_chat(user_id=user_id, prompt=payload.message)

    result = await cascade_router.process_query(user_id=user_id, prompt=payload.message)

    trace.update(output=result["text"], metadata={"source": result["source"]})

    async with async_session_maker() as session:
        message = MessageModel(
            user_id=user_id,
            telegram_message_id=None,
            prompt=payload.message,
            response=result["text"],
            source=result["source"],
            context_used=result["context_used"],
            rag_debug=result.get("rag_debug"),
            timing=result.get("timing"),
            rag_trace_id=result.get("rag_trace_id"),
        )
        session.add(message)
        await session.flush()
        trace_events = result.get("trace_events")
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
        await session.commit()

    return ChatResponse(
        choices=[ChatChoice(index=0, message=ChatMessage(role="assistant", content=result["text"]))],
        source=result["source"],
        context_used=result["context_used"],
    )
