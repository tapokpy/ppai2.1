import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.services.local_llm import LocalLLMClient

TIME_PATTERN = re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b")
RELATIVE_PATTERN = re.compile(
    r"через\s+(?P<amount>\d+)\s*(?P<unit>минут(?:у|ы)?|мин|час(?:а|ов)?)", re.IGNORECASE
)
MENTION_PATTERN = re.compile(r"@(?P<username>\w+)")

LLM_SYSTEM_PROMPT = (
    "Извлеки из сообщения информацию о напоминании и верни строго JSON без пояснений: "
    '{{"has_reminder": bool, "datetime_iso": str|null, "cron_expression": str|null, '
    '"target_username": str|null, "task_text": str}}. Текущее время: {current_time}."'
)


@dataclass
class ParsedReminder:
    has_reminder: bool
    datetime_iso: str | None = None
    cron_expression: str | None = None
    target_username: str | None = None
    task_text: str = ""


def parse_reminder(text: str, current_time: datetime) -> ParsedReminder:
    mention_match = MENTION_PATTERN.search(text)
    target_username = f"@{mention_match.group('username')}" if mention_match else None
    task_text = MENTION_PATTERN.sub("", text).strip()

    time_match = TIME_PATTERN.search(text)
    if time_match:
        hour, minute = int(time_match.group("hour")), int(time_match.group("minute"))
        notify_at = current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if notify_at <= current_time:
            notify_at += timedelta(days=1)
        task_text = TIME_PATTERN.sub("", task_text).strip()
        return ParsedReminder(
            has_reminder=True,
            datetime_iso=notify_at.isoformat(),
            target_username=target_username,
            task_text=task_text,
        )

    relative_match = RELATIVE_PATTERN.search(text)
    if relative_match:
        amount = int(relative_match.group("amount"))
        unit = relative_match.group("unit")
        delta = timedelta(hours=amount) if unit.startswith("час") else timedelta(minutes=amount)
        notify_at = current_time + delta
        task_text = RELATIVE_PATTERN.sub("", task_text).strip()
        return ParsedReminder(
            has_reminder=True,
            datetime_iso=notify_at.isoformat(),
            target_username=target_username,
            task_text=task_text,
        )

    return ParsedReminder(has_reminder=False, target_username=target_username, task_text=task_text)


async def parse_reminder_with_llm_fallback(
    text: str, current_time: datetime, local_llm: LocalLLMClient
) -> ParsedReminder:
    regex_result = parse_reminder(text, current_time)
    if regex_result.has_reminder:
        return regex_result

    raw = await local_llm.generate(
        prompt=text,
        system_prompt=LLM_SYSTEM_PROMPT.format(current_time=current_time.isoformat()),
    )

    data = _try_parse_json(raw)
    if data is None:
        return ParsedReminder(has_reminder=False, task_text=text)

    return ParsedReminder(
        has_reminder=bool(data.get("has_reminder", False)),
        datetime_iso=data.get("datetime_iso"),
        cron_expression=data.get("cron_expression"),
        target_username=data.get("target_username"),
        task_text=data.get("task_text", text),
    )


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
