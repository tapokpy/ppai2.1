from unittest.mock import patch

from app.bot.main import build_cascade_router, build_dispatcher
from app.core.router import CascadeRouter


def test_build_dispatcher_registers_all_routers():
    dp = build_dispatcher()

    included_names = {router.name for router in dp.sub_routers}

    assert included_names == {"start", "admin", "engineer", "chat"}


def test_build_cascade_router_wires_dependencies():
    with (
        patch("app.bot.main.RAGEngine") as rag_cls,
        patch("app.bot.main.default_embedding_function"),
        patch("app.bot.main.LocalLLMClient") as local_cls,
        patch("app.bot.main.CloudLLMClient") as cloud_cls,
        patch("app.bot.main.Redis") as redis_cls,
    ):
        router = build_cascade_router()

    assert isinstance(router, CascadeRouter)
    rag_cls.assert_called_once()
    local_cls.assert_called_once()
    cloud_cls.assert_called_once()
    redis_cls.from_url.assert_called_once()
