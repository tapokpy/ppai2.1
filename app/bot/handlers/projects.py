from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.database import async_session_maker
from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.models.sqlalchemy.project import Project

router = Router(name="projects")

PROJECT_NEW_USAGE = "Использование: /project_new <название>[; заказчик]"
PROJECT_ATTACH_USAGE = "Использование: /project_attach <ID проекта> <ID чертежа>"
NO_PROJECTS_REPLY = "Проектов пока нет. Создайте: /project_new <название>"


@router.message(Command("project_new"))
async def cmd_project_new(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    if not command.args:
        await message.answer(PROJECT_NEW_USAGE)
        return

    name, _, customer = command.args.partition(";")
    name = name.strip()
    customer = customer.strip() or None
    if not name:
        await message.answer(PROJECT_NEW_USAGE)
        return

    async with async_session_maker() as session:
        project = Project(name=name, customer=customer)
        session.add(project)
        await session.commit()
        await session.refresh(project)

    await message.answer(f"Проект «{project.name}» создан, ID {project.id}.")


@router.message(Command("project_list"))
async def cmd_project_list(message: Message) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()).limit(20))
        projects = result.scalars().all()

    if not projects:
        await message.answer(NO_PROJECTS_REPLY)
        return

    lines = [f"#{p.id} «{p.name}»" + (f" — {p.customer}" if p.customer else "") for p in projects]
    await message.answer("\n".join(lines))


@router.message(Command("project_attach"))
async def cmd_project_attach(message: Message, command: CommandObject) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer(PROJECT_ATTACH_USAGE)
        return

    try:
        project_id, doc_id = int(parts[0]), int(parts[1])
    except ValueError:
        await message.answer(PROJECT_ATTACH_USAGE)
        return

    async with async_session_maker() as session:
        project = await session.get(Project, project_id)
        doc = await session.get(EngineeringDoc, doc_id)

        if project is None:
            await message.answer(f"Проект #{project_id} не найден.")
            return
        if doc is None:
            await message.answer(f"Чертёж #{doc_id} не найден.")
            return

        doc.project_id = project.id
        await session.commit()

    await message.answer(f"Чертёж «{doc.project_name}» привязан к проекту «{project.name}».")
