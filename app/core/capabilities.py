from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


def _load_capability_entries(path: str) -> list[dict[str, Any]]:
    """Not cached itself — load_capabilities_summary and
    format_capabilities_for_user each cache their own small rendering, so
    re-parsing here on either one's cache miss is cheap and avoids having
    to keep two separate caches in sync."""
    file_path = Path(path)
    if not file_path.exists():
        return []

    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning(f"capabilities.yaml at {path} is malformed, ignoring: {exc}")
        return []

    return data.get("capabilities") or []


def _capability_lines(path: str) -> list[str]:
    return [
        f"- {entry['name']}: {entry['description']}"
        for entry in _load_capability_entries(path)
        if entry.get("name") and entry.get("description")
    ]


@lru_cache(maxsize=4)
def load_capabilities_summary(path: str) -> str:
    """Renders capabilities.yaml as a compact bullet list for the system
    prompt (second-person "ты" — addressed to the LLM, not the end user;
    see format_capabilities_for_user for the user-facing version). Cached
    per path for the process lifetime — matches the spec's "loads at
    startup" framing without threading a loaded-once object through every
    call site's dependency wiring. Missing/empty file is not an error,
    just an empty capabilities block.

    Called on every single chat message (app/core/prompt_manager.py ->
    app/core/router.py::_process_query), so a malformed file must degrade
    to the same empty-block fallback as a missing one rather than raise —
    lru_cache never caches an exception, so an uncaught error here would
    re-parse (and re-fail) on every message instead of failing once."""
    lines = _capability_lines(path)
    if not lines:
        return ""

    return "Возможности системы «Папай», которыми ты реально располагаешь:\n" + "\n".join(lines)


@lru_cache(maxsize=4)
def format_capabilities_for_user(path: str) -> str:
    """First-person, user-facing rendering of the same capabilities.yaml —
    used to answer "умеешь ли ты...?" questions deterministically
    (app/core/router.py, when app.core.prompt_manager.is_capability_question
    matches) instead of asking a small local LLM to faithfully reproduce a
    list it's given. That was tried first and failed live: the model
    ignored the list and answered from its own generic training-data
    priors about what "an AI" can/can't do, occasionally in Chinese."""
    lines = _capability_lines(path)
    if not lines:
        return "Список возможностей сейчас недоступен — обратитесь к администратору."

    return "Вот что я умею:\n" + "\n".join(lines)
