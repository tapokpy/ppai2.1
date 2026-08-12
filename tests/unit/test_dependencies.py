from unittest.mock import patch

from app.core.dependencies import build_cascade_router, build_github_planning_client, build_transcriber
from app.core.router import CascadeRouter
from app.services.github_planning import GitHubPlanningClient
from app.services.stt import Transcriber


def test_build_cascade_router_wires_dependencies():
    with (
        patch("app.core.dependencies.RAGEngine") as rag_cls,
        patch("app.core.dependencies.default_embedding_function"),
        patch("app.core.dependencies.LocalLLMClient") as local_cls,
        patch("app.core.dependencies.CloudLLMClient") as cloud_cls,
        patch("app.core.dependencies.Redis") as redis_cls,
    ):
        router = build_cascade_router()

    assert isinstance(router, CascadeRouter)
    rag_cls.assert_called_once()
    local_cls.assert_called_once()
    cloud_cls.assert_called_once()
    redis_cls.from_url.assert_called_once()


def test_build_transcriber_returns_transcriber_instance():
    transcriber = build_transcriber()

    assert isinstance(transcriber, Transcriber)


def test_build_github_planning_client_returns_client_instance():
    client = build_github_planning_client()

    assert isinstance(client, GitHubPlanningClient)
