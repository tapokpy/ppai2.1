from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.documents import handle_document
from app.core.database import async_session_maker
from app.models.sqlalchemy.project import Project
from app.models.sqlalchemy.project_file import ProjectFile
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres

ADMIN_ID = 970
NON_ADMIN_ID = 971


def _message(caption: str | None, user_id: int = ADMIN_ID, file_name: str = "screens.ini"):
    return SimpleNamespace(
        document=SimpleNamespace(file_id="f1", file_name=file_name, mime_type="application/octet-stream"),
        caption=caption,
        from_user=SimpleNamespace(id=user_id),
        answer=AsyncMock(),
    )


async def _seed_project() -> Project:
    async with async_session_maker() as session:
        project = Project(name="Объект 1")
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_project_file_caption_routes_before_extension_checks(clean_db, tmp_path):
    project = await _seed_project()
    message = _message(caption=f"проект3 {project.id}")
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="remote/f1.ini")),
        download_file=AsyncMock(),
    )

    with patch("app.bot.handlers.admin.settings") as admin_settings_mock, patch(
        "app.bot.handlers.documents.settings"
    ) as doc_settings_mock:
        admin_settings_mock.admin_ids = [ADMIN_ID]
        doc_settings_mock.PROJECT_FILES_PATH = str(tmp_path)
        await handle_document(message, bot, cascade_router=None, db_user=None)

    async with async_session_maker() as session:
        files = (await session.execute(select(ProjectFile))).scalars().all()

    assert len(files) == 1
    assert files[0].project_id == project.id
    assert files[0].file_name == "screens.ini"
    assert "прикреплён" in message.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_project_file_upload_requires_admin(clean_db, tmp_path):
    project = await _seed_project()
    message = _message(caption=f"проект3 {project.id}", user_id=NON_ADMIN_ID)
    bot = SimpleNamespace(get_file=AsyncMock(), download_file=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as admin_settings_mock:
        admin_settings_mock.admin_ids = [ADMIN_ID]
        await handle_document(message, bot, cascade_router=None, db_user=None)

    assert "администратор" in message.answer.call_args.args[0].lower()
    bot.get_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_project_file_upload_unknown_project(clean_db, tmp_path):
    message = _message(caption="проект3 99999")
    bot = SimpleNamespace(get_file=AsyncMock(), download_file=AsyncMock())

    with patch("app.bot.handlers.admin.settings") as admin_settings_mock:
        admin_settings_mock.admin_ids = [ADMIN_ID]
        await handle_document(message, bot, cascade_router=None, db_user=None)

    assert "не найден" in message.answer.call_args.args[0]
