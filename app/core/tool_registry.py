import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass
class ToolParameter:
    name: str
    type: str  # JSON-schema primitive: "string" | "number" | "integer" | "boolean"
    description: str
    required: bool = True


@dataclass
class ToolAttachment:
    """A file the tool result should be sent as, e.g. a downloaded video or
    a rendered chart. Only the Telegram handler acts on this — the web
    /api/v1/chat endpoint has no attachment concept and ignores it."""

    file_path: str
    kind: str  # "document" | "video" | "photo"


@dataclass
class ToolResult:
    text: str
    success: bool = True
    error: str | None = None
    structured_data: dict[str, Any] | None = None
    attachment: ToolAttachment | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: list[ToolParameter]
    handler: Callable[..., Awaitable[ToolResult]]
    admin_only: bool = False

    def to_ollama_function(self) -> dict:
        properties = {
            p.name: {"type": p.type, "description": p.description} for p in self.parameters
        }
        required = [p.name for p in self.parameters if p.required]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    def to_prompt_line(self) -> str:
        params = ", ".join(f"{p.name}: {p.type}{'' if p.required else '?'}" for p in self.parameters)
        return f"- {self.name}({params}) — {self.description}"


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_for(self, is_admin: bool) -> list[ToolSpec]:
        return [t for t in self._tools.values() if is_admin or not t.admin_only]

    def to_ollama_schema(self, is_admin: bool) -> list[dict]:
        return [t.to_ollama_function() for t in self.list_for(is_admin)]

    def to_prompt_block(self, is_admin: bool) -> str:
        tools = self.list_for(is_admin)
        if not tools:
            return ""
        lines = [t.to_prompt_line() for t in tools]
        return (
            "Доступные функции — если запрос пользователя явно просит выполнить одно из "
            "этих действий, ответь СТРОГО JSON без пояснений: "
            '{"tool": "<имя функции>", "arguments": {...}}\n'
            "Если ни одна функция не подходит, ответь обычным текстом, не JSON.\n"
            "Функции:\n" + "\n".join(lines)
        )


def try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
