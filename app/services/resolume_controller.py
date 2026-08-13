from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml
from loguru import logger
from pythonosc.udp_client import SimpleUDPClient


class ResolumeUnavailableError(Exception):
    """Raised when the OSC socket itself can't be opened/sent to. Note OSC
    is a fire-and-forget UDP protocol: a successful send does NOT confirm
    Resolume actually received or executed the command — only that this
    process put a packet on the wire. Use ResolumeController.is_reachable()
    (REST) beforehand for an actual liveness signal."""


class ScreenNotFoundError(Exception):
    """Raised when a screen/preset name isn't in screens_map.yaml. Callers
    (the showroom chat handler) should turn this into the spec's required
    clarifying question rather than silently failing."""


@dataclass
class ScreenTarget:
    layer: int


class ScreensMap:
    """Loads the friendly-name -> Resolume layer mapping from
    screens_map.yaml. A screen's layer is fixed (which physical output a
    layer feeds), but *which clip* plays is always supplied at trigger
    time — either the column the user names directly, or a preset step's
    column — never a fixed "default column" on the screen itself. Missing/
    empty file is not an error — showroom control just has nothing
    configured yet (expected: "настройку резолюм оставим на потом")."""

    def __init__(self, screens: dict[str, ScreenTarget], presets: dict[str, list[dict]]):
        self._screens = screens
        self._presets = presets

    @classmethod
    def load(cls, path: str) -> "ScreensMap":
        file_path = Path(path)
        if not file_path.exists():
            logger.warning(f"screens_map.yaml not found at {path} — no showroom screens configured yet")
            return cls(screens={}, presets={})

        data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
        screens = {
            name: ScreenTarget(layer=info["layer"]) for name, info in (data.get("screens") or {}).items()
        }
        presets = data.get("presets") or {}
        return cls(screens=screens, presets=presets)

    @property
    def screen_names(self) -> list[str]:
        return list(self._screens)

    @property
    def preset_names(self) -> list[str]:
        return list(self._presets)

    def get_screen(self, name: str) -> ScreenTarget:
        try:
            return self._screens[name]
        except KeyError:
            raise ScreenNotFoundError(name) from None

    def get_preset_steps(self, name: str) -> list[tuple[int, int]]:
        """Returns (layer, column) pairs to trigger for a named preset."""
        try:
            steps = self._presets[name]
        except KeyError:
            raise ScreenNotFoundError(name) from None
        return [(self.get_screen(step["screen"]).layer, step["column"]) for step in steps]


class ResolumeController:
    def __init__(self, osc_host: str, osc_port: int, rest_base_url: str):
        self._osc_host = osc_host
        self._osc_port = osc_port
        self._rest_base_url = rest_base_url

    def trigger_clip(self, layer: int, column: int) -> None:
        """Fires Resolume's documented OSC address for connecting a clip:
        /composition/layers/{layer}/clips/{column}/connect."""
        try:
            client = SimpleUDPClient(self._osc_host, self._osc_port)
            client.send_message(f"/composition/layers/{layer}/clips/{column}/connect", 1)
        except OSError as exc:
            raise ResolumeUnavailableError(str(exc)) from exc

    async def is_reachable(self) -> bool:
        """Best-effort REST health check — the only way to actually confirm
        Resolume is up, since OSC gives no delivery confirmation."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self._rest_base_url}/composition")
                return response.status_code == 200
        except httpx.HTTPError:
            return False
