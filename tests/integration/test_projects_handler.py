from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.bot.handlers.projects import cmd_project_attach, cmd_project_list, cmd_project_new
from app.core.database import async_session_maker
from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.models.sqlalchemy.project import Project
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres

ADMIN_ID = 950
NON_ADMIN_ID = 951


def _message(user_id: int = NON_ADMIN_ID):
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id), answer=AsyncMock())


@pytest.mark.asyncio
async def test_project_new_rejects_non_admin(clean_db):
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(NON_ADMIN_ID)
        await cmd_project_new(message, SimpleNamespace(args="Объект 1"))

    assert "администратор" in message.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_project_new_creates_project_with_customer(clean_db):
    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(ADMIN_ID)
        await cmd_project_new(message, SimpleNamespace(args="Объект 1; ООО Ромашка"))

    async with async_session_maker() as session:
        projects = (await session.execute(select(Project))).scalars().all()

    assert len(projects) == 1
    assert projects[0].name == "Объект 1"
    assert projects[0].customer == "ООО Ромашка"


@pytest.mark.asyncio
async def test_project_list_shows_no_projects_message(clean_db):
    message = _message(NON_ADMIN_ID)
    await cmd_project_list(message)
    assert "нет" in message.answer.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_project_attach_links_engineering_doc(clean_db):
    async with async_session_maker() as session:
        project = Project(name="Объект 1")
        doc = EngineeringDoc(project_name="drawing_1", file_path="/x.dxf", doc_type="dxf", is_generated=True)
        session.add_all([project, doc])
        await session.commit()
        await session.refresh(project)
        await session.refresh(doc)

    with patch("app.bot.handlers.admin.settings") as settings_mock:
        settings_mock.admin_ids = [ADMIN_ID]
        message = _message(ADMIN_ID)
        await cmd_project_attach(message, SimpleNamespace(args=f"{project.id} {doc.id}"))

    async with async_session_maker() as session:
        refreshed_doc = await session.get(EngineeringDoc, doc.id)

    assert refreshed_doc.project_id == project.id
