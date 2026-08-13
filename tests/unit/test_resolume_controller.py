from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.resolume_controller import (
    ResolumeController,
    ResolumeUnavailableError,
    ScreenNotFoundError,
    ScreensMap,
)


def test_screens_map_load_missing_file_returns_empty(tmp_path):
    screens_map = ScreensMap.load(str(tmp_path / "nope.yaml"))

    assert screens_map.screen_names == []
    assert screens_map.preset_names == []


def test_screens_map_load_parses_screens_and_presets(tmp_path):
    config = tmp_path / "screens_map.yaml"
    config.write_text(
        """
screens:
  Главный фасад:
    layer: 1
  Левый пилон:
    layer: 2

presets:
  Ночной режим:
    - screen: Главный фасад
      column: 3
    - screen: Левый пилон
      column: 3
""",
        encoding="utf-8",
    )

    screens_map = ScreensMap.load(str(config))

    assert set(screens_map.screen_names) == {"Главный фасад", "Левый пилон"}
    assert screens_map.preset_names == ["Ночной режим"]
    assert screens_map.get_screen("Главный фасад").layer == 1


def test_screens_map_get_screen_raises_for_unknown_name(tmp_path):
    screens_map = ScreensMap.load(str(tmp_path / "nope.yaml"))

    with pytest.raises(ScreenNotFoundError):
        screens_map.get_screen("Неизвестный экран")


def test_screens_map_get_preset_steps_resolves_layers(tmp_path):
    config = tmp_path / "screens_map.yaml"
    config.write_text(
        """
screens:
  A:
    layer: 1
  B:
    layer: 2
presets:
  P:
    - screen: A
      column: 5
    - screen: B
      column: 7
""",
        encoding="utf-8",
    )
    screens_map = ScreensMap.load(str(config))

    steps = screens_map.get_preset_steps("P")

    assert steps == [(1, 5), (2, 7)]


def test_screens_map_get_preset_steps_raises_for_unknown_preset(tmp_path):
    screens_map = ScreensMap.load(str(tmp_path / "nope.yaml"))

    with pytest.raises(ScreenNotFoundError):
        screens_map.get_preset_steps("Неизвестный пресет")


def test_trigger_clip_sends_correct_osc_address():
    controller = ResolumeController(osc_host="127.0.0.1", osc_port=7000, rest_base_url="http://x")
    mock_client = MagicMock()

    with patch("app.services.resolume_controller.SimpleUDPClient", return_value=mock_client):
        controller.trigger_clip(layer=2, column=5)

    mock_client.send_message.assert_called_once_with("/composition/layers/2/clips/5/connect", 1)


def test_trigger_clip_wraps_os_error():
    controller = ResolumeController(osc_host="127.0.0.1", osc_port=7000, rest_base_url="http://x")

    with patch("app.services.resolume_controller.SimpleUDPClient", side_effect=OSError("bad host")):
        with pytest.raises(ResolumeUnavailableError):
            controller.trigger_clip(layer=1, column=1)


@pytest.mark.asyncio
async def test_is_reachable_true_on_200():
    controller = ResolumeController(osc_host="x", osc_port=7000, rest_base_url="http://resolume/api/v1")
    mock_response = MagicMock(status_code=200)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.resolume_controller.httpx.AsyncClient", return_value=mock_client):
        assert await controller.is_reachable() is True


@pytest.mark.asyncio
async def test_is_reachable_false_on_connection_error():
    controller = ResolumeController(osc_host="x", osc_port=7000, rest_base_url="http://resolume/api/v1")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.resolume_controller.httpx.AsyncClient", return_value=mock_client):
        assert await controller.is_reachable() is False
