from typing import Any

from pydantic import BaseModel


class SourceCount(BaseModel):
    source: str
    count: int


class AnalyticsResponse(BaseModel):
    total_users: int
    approved_users: int
    total_messages: int
    messages_by_source: list[SourceCount]


class RagTraceResponse(BaseModel):
    message_id: int
    source: str
    prompt: str
    rag_debug: dict[str, Any] | None
