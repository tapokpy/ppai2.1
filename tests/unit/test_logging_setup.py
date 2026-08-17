from unittest.mock import MagicMock, patch

from app.core.logging_setup import configure_file_logging


def test_configure_file_logging_creates_log_dir_and_adds_sink(tmp_path):
    log_dir = tmp_path / "logs"

    with (
        patch("app.core.logging_setup.settings.LOG_STORAGE_PATH", str(log_dir)),
        patch("app.core.logging_setup.logger.add") as add_mock,
    ):
        configure_file_logging("bot")

    assert log_dir.exists()
    add_mock.assert_called_once()
    sink_path = add_mock.call_args.args[0]
    assert sink_path == log_dir / "bot.log"


def test_configure_file_logging_uses_service_name_in_filename(tmp_path):
    log_dir = tmp_path / "logs"

    with (
        patch("app.core.logging_setup.settings.LOG_STORAGE_PATH", str(log_dir)),
        patch("app.core.logging_setup.logger", MagicMock()) as logger_mock,
    ):
        configure_file_logging("api")

    sink_path = logger_mock.add.call_args.args[0]
    assert sink_path.name == "api.log"
