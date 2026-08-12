from datetime import datetime
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


class TraceEventResponse(BaseModel):
    seq: int
    event_name: str
    payload: dict[str, Any]
    created_at: datetime


class RagTraceResponse(BaseModel):
    message_id: int
    source: str
    prompt: str
    rag_debug: dict[str, Any] | None
    rag_trace_id: str | None = None
    timing: dict[str, float] | None = None
    events: list[TraceEventResponse] = []


class MessageSummary(BaseModel):
    id: int
    created_at: datetime
    user_id: int
    source: str
    prompt: str
    context_used: bool


class MessageListResponse(BaseModel):
    items: list[MessageSummary]
    total: int


class DocumentSummary(BaseModel):
    id: int
    source: str
    filename: str | None
    chunk_count: int
    status: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentSummary]
    total: int


class ChunkResponse(BaseModel):
    chunk_id: str
    text: str
    metadata: dict[str, Any]


class DocumentDetailResponse(BaseModel):
    document: DocumentSummary
    embedding_model: str
    collection: str
    chunks: list[ChunkResponse]
