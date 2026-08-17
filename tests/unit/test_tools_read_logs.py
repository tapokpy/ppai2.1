from unittest.mock import patch

import pytest

from app.services.tools import read_logs_tool


@pytest.mark.asyncio
async def test_run_returns_last_n_lines(tmp_path):
    log_file = tmp_path / "bot.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(1, 251)), encoding="utf-8")

    with patch("app.services.tools.read_logs_tool.settings.LOG_STORAGE_PATH", str(tmp_path)):
        result = await read_logs_tool.run(service="bot", lines=5)

    assert result.success is True
    assert "line 246" in result.text
    assert "line 250" in result.text
    assert "line 245" not in result.text


@pytest.mark.asyncio
async def test_run_caps_lines_at_max(tmp_path):
    log_file = tmp_path / "bot.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(1, 500)), encoding="utf-8")

    with patch("app.services.tools.read_logs_tool.settings.LOG_STORAGE_PATH", str(tmp_path)):
        result = await read_logs_tool.run(service="bot", lines=10000)

    assert "Последние 300 строк" in result.text


@pytest.mark.asyncio
async def test_run_defaults_to_bot_service(tmp_path):
    (tmp_path / "bot.log").write_text("привет из bot", encoding="utf-8")

    with patch("app.services.tools.read_logs_tool.settings.LOG_STORAGE_PATH", str(tmp_path)):
        result = await read_logs_tool.run()

    assert "привет из bot" in result.text


@pytest.mark.asyncio
async def test_run_reports_missing_log_file(tmp_path):
    with patch("app.services.tools.read_logs_tool.settings.LOG_STORAGE_PATH", str(tmp_path)):
        result = await read_logs_tool.run(service="api")

    assert "ещё не создан" in result.text


@pytest.mark.asyncio
async def test_run_rejects_unknown_service(tmp_path):
    with patch("app.services.tools.read_logs_tool.settings.LOG_STORAGE_PATH", str(tmp_path)):
        result = await read_logs_tool.run(service="postgres")

    assert result.success is False
    assert "Неизвестный сервис" in result.text


def test_tool_spec_is_admin_only():
    assert read_logs_tool.TOOL_SPEC.admin_only is True


def test_tool_spec_has_optional_parameters():
    params = {p.name: p.required for p in read_logs_tool.TOOL_SPEC.parameters}
    assert params == {"service": False, "lines": False}
