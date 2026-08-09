from typing import Any, Protocol

from app.core.config import settings


class ChatTrace(Protocol):
    def update(self, **kwargs: Any) -> None: ...


class NullTrace:
    def update(self, **kwargs: Any) -> None:
        pass


class ChatTracer:
    def __init__(self) -> None:
        self._enabled = bool(settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)
        self._client = None
        if self._enabled:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST or None,
            )

    def trace_chat(self, *, user_id: int, prompt: str) -> ChatTrace:
        if not self._enabled:
            return NullTrace()

        return self._client.trace(name="web_chat", user_id=str(user_id), input=prompt)


def get_tracer() -> ChatTracer:
    return ChatTracer()
