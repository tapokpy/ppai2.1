from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.reminder_parser import parse_reminder, parse_reminder_with_llm_fallback

NOON = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def test_parse_reminder_extracts_time_today():
    result = parse_reminder("15:00 Проверить блоки питания", NOON)

    assert result.has_reminder is True
    assert result.datetime_iso == "2026-08-09T15:00:00+00:00"
    assert result.task_text == "Проверить блоки питания"
    assert result.target_username is None


def test_parse_reminder_rolls_over_to_tomorrow_when_time_passed():
    result = parse_reminder("10:00 Утренний отчёт", NOON)

    assert result.datetime_iso == "2026-08-10T10:00:00+00:00"


def test_parse_reminder_extracts_mention():
    result = parse_reminder("15:00 @nikolia скинуть смету", NOON)

    assert result.target_username == "@nikolia"
    assert "@nikolia" not in result.task_text
    assert "скинуть смету" in result.task_text


def test_parse_reminder_extracts_relative_minutes():
    result = parse_reminder("через 10 минут проверить экран", NOON)

    assert result.has_reminder is True
    assert result.datetime_iso == "2026-08-09T12:10:00+00:00"


def test_parse_reminder_extracts_relative_hours():
    result = parse_reminder("через 2 часа перезвонить клиенту", NOON)

    assert result.datetime_iso == "2026-08-09T14:00:00+00:00"


def test_parse_reminder_returns_no_reminder_for_unparseable_text():
    result = parse_reminder("напомни завтра в 10 утра скинуть смету Николе", NOON)

    assert result.has_reminder is False


@pytest.mark.asyncio
async def test_llm_fallback_used_only_when_regex_fails():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock()

    result = await parse_reminder_with_llm_fallback("15:00 Проверить блоки питания", NOON, local_llm)

    assert result.has_reminder is True
    local_llm.generate.assert_not_called()


@pytest.mark.asyncio
async def test_llm_fallback_parses_valid_json_response():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(
        return_value=(
            '{"has_reminder": true, "datetime_iso": "2026-08-10T10:00:00+00:00", '
            '"cron_expression": null, "target_username": "@nikolia", "task_text": "Скинуть смету"}'
        )
    )

    result = await parse_reminder_with_llm_fallback(
        "напомни завтра в 10 утра скинуть смету Николе", NOON, local_llm
    )

    assert result.has_reminder is True
    assert result.datetime_iso == "2026-08-10T10:00:00+00:00"
    assert result.target_username == "@nikolia"
    assert result.task_text == "Скинуть смету"


@pytest.mark.asyncio
async def test_llm_fallback_handles_invalid_json_gracefully():
    local_llm = AsyncMock()
    local_llm.generate = AsyncMock(return_value="это не JSON")

    result = await parse_reminder_with_llm_fallback("бессмысленный текст без времени", NOON, local_llm)

    assert result.has_reminder is False
