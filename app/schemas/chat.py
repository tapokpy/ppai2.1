from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatResponse(BaseModel):
    object: str = "chat.completion"
    choices: list[ChatChoice]
    source: str
    context_used: bool
