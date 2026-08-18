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


@dataclass
class ColumnInfo:
    column: int
    name: str


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

    def trigger_column(self, column: int) -> None:
        """Fires Resolume's documented OSC address for connecting an entire
        column: /composition/columns/{column}/connect — triggers every
        layer's clip in that column at once (a scene switch), unlike
        trigger_clip which only affects one named layer. This is the
        right call for a single physical screen composited from several
        layers (background/overlay/text), where "switch to clip N" means
        "activate column N across the whole composition", not "change
        just one layer and leave the others as they were."""
        try:
            client = SimpleUDPClient(self._osc_host, self._osc_port)
            client.send_message(f"/composition/columns/{column}/connect", 1)
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

    async def list_occupied_columns(self) -> list[ColumnInfo]:
        """Fetches the live composition over REST and returns every column
        that has a real clip loaded in at least one layer (state != Empty),
        in column order — lets the showroom handler show real, tappable
        buttons instead of asking the user to guess a column number blind.
        A column can have a named clip in one layer and nothing in the
        others (e.g. only the "text" layer is named in the observed live
        composition) — the first non-empty name found for that column
        wins; falls back to "Ролик N" if the clip exists but was never
        named in Resolume."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._rest_base_url}/composition")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ResolumeUnavailableError(str(exc)) from exc

        names_by_column: dict[int, str] = {}
        for layer in data.get("layers", []):
            for i, clip in enumerate(layer.get("clips", []), start=1):
                state = (clip.get("connected") or {}).get("value")
                if not state or state == "Empty":
                    continue
                name = (clip.get("name") or {}).get("value") or ""
                if i not in names_by_column or (not names_by_column[i] and name):
                    names_by_column[i] = name

        return [
            ColumnInfo(column=column, name=names_by_column[column] or f"Ролик {column}")
            for column in sorted(names_by_column)
        ]
