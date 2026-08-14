from functools import lru_cache
from pathlib import Path

import yaml
from loguru import logger


@lru_cache(maxsize=4)
def load_capabilities_summary(path: str) -> str:
    """Renders capabilities.yaml as a compact bullet list for the system
    prompt. Cached per path for the process lifetime — matches the spec's
    "loads at startup" framing without threading a loaded-once object
    through every call site's dependency wiring. Missing/empty file is not
    an error, just an empty capabilities block.

    Called on every single chat message (app/core/prompt_manager.py ->
    app/core/router.py::_process_query), so a malformed file must degrade
    to the same empty-block fallback as a missing one rather than raise —
    lru_cache never caches an exception, so an uncaught error here would
    re-parse (and re-fail) on every message instead of failing once."""
    file_path = Path(path)
    if not file_path.exists():
        return ""

    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning(f"capabilities.yaml at {path} is malformed, ignoring: {exc}")
        return ""

    entries = data.get("capabilities") or []

    lines = [
        f"- {entry['name']}: {entry['description']}"
        for entry in entries
        if entry.get("name") and entry.get("description")
    ]
    if not lines:
        return ""

    return "Возможности системы «Папай», которыми ты реально располагаешь:\n" + "\n".join(lines)
