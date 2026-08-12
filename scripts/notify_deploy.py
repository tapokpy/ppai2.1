"""Sends admins a short Telegram summary of what changed in a deploy.

Run as the last step after rebuilding/restarting bot/api, same pattern as
the live curl/docker-exec verification already done after every change in
this project — this just also tells the admins about it in the same chat
they use the bot from, instead of only being visible in this session.

    docker exec ppai-bot-1 python -m scripts.notify_deploy \
        "- Исправлена галлюцинация RAG на запросах про «ПридПром»" \
        "- Включено GPU-ускорение Ollama" \
        --services bot,api

A standalone script (not part of the bot process) so it can be invoked at
any point during a deploy, not just at startup like
app.bot.main.notify_admins_of_restart.
"""
import argparse
import asyncio
import sys

import httpx
from loguru import logger

from app.core.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org"


def _format_message(bullets: list[str], services: str | None) -> str:
    body = "🔧 Обновление ppai\n\n" + "\n".join(bullets)
    if services:
        body += f"\n\nДеплой: {services}"
    return body


async def notify_deploy(bullets: list[str], services: str | None = None) -> None:
    message = _format_message(bullets, services)

    async with httpx.AsyncClient() as client:
        for admin_id in settings.admin_ids:
            try:
                response = await client.post(
                    f"{TELEGRAM_API_BASE}/bot{settings.BOT_TOKEN}/sendMessage",
                    json={"chat_id": admin_id, "text": message},
                    timeout=10.0,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(f"Failed to notify admin {admin_id} of deploy: {exc}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bullets", nargs="+", help="One or more summary lines (e.g. '- fixed X')")
    parser.add_argument("--services", default=None, help="Comma-separated services redeployed, e.g. bot,api")
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args(sys.argv[1:])
    asyncio.run(notify_deploy(args.bullets, args.services))


if __name__ == "__main__":
    main()
