from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy import select

from app.bot.fsm.calculators import BomCalculatorStates
from app.bot.handlers.admin import ACCESS_DENIED_MESSAGE, is_admin
from app.core.database import async_session_maker
from app.models.sqlalchemy.engineering_doc import EngineeringDoc
from app.models.sqlalchemy.project import Project
from app.models.sqlalchemy.user import User
from app.services.audit import log_action
from app.services.bom_reconciliation import build_pick_list, check_bom_against_stock, format_deficits

router = Router(name="projects")

PROJECT_NEW_USAGE = "Использование: /project_new <название>[; заказчик]"
PROJECT_ATTACH_USAGE = "Использование: /project_attach <ID проекта> <ID чертежа>"
NO_PROJECTS_REPLY = "Проектов пока нет. Создайте: /project_new <название>"
PROJECT_BOM_USAGE = "Использование: /project_bom <ID проекта>"
PROJECT_ID_USAGE = "Использование: {command} <ID проекта>"
NO_BOM_REPLY = "У проекта ещё нет расчёта BOM. Сначала выполните: /project_bom {project_id}"


@router.message(Command("project_new"))
async def cmd_project_new(message: Message, command: CommandObject, db_user: User) -> None:
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
        await log_action(
            session,
            user_id=db_user.id,
            command_text=f"/project_new {command.args.strip()}",
            module="projects",
            decision="project_created",
            detail={"project_id": project.id},
        )

    await message.answer(f"Проект «{project.name}» создан, ID {project.id}.")


async def _list_projects(message: Message) -> None:
    async with async_session_maker() as session:
        result = await session.execute(select(Project).order_by(Project.created_at.desc()).limit(20))
        projects = result.scalars().all()

    if not projects:
        await message.answer(NO_PROJECTS_REPLY)
        return

    lines = [f"#{p.id} «{p.name}»" + (f" — {p.customer}" if p.customer else "") for p in projects]
    await message.answer("\n".join(lines))


@router.message(Command("project_list"))
async def cmd_project_list(message: Message) -> None:
    await _list_projects(message)


@router.message(Command("project_attach"))
async def cmd_project_attach(message: Message, command: CommandObject, db_user: User) -> None:
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
        await log_action(
            session,
            user_id=db_user.id,
            command_text=f"/project_attach {project_id} {doc_id}",
            module="projects",
            decision="doc_attached",
        )

    await message.answer(f"Чертёж «{doc.project_name}» привязан к проекту «{project.name}».")


async def _resolve_project_id(message: Message, command: CommandObject, usage: str) -> int | None:
    if not command.args:
        await message.answer(usage)
        return None
    try:
        return int(command.args.strip().split()[0])
    except ValueError:
        await message.answer(usage)
        return None


@router.message(Command("project_bom"))
async def cmd_project_bom(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(ACCESS_DENIED_MESSAGE)
        return

    project_id = await _resolve_project_id(message, command, PROJECT_BOM_USAGE)
    if project_id is None:
        return

    async with async_session_maker() as session:
        project = await session.get(Project, project_id)
    if project is None:
        await message.answer(f"Проект #{project_id} не найден.")
        return

    # Consumed by app.bot.handlers.engineer._finish_bom_calculation once the
    # FSM dialog completes — that's the only place bom_target_project_id
    # is read, so it's safe to store here and let the calculator flow
    # (registered on the same dispatcher, same FSM storage) pick it up.
    await state.update_data(bom_target_project_id=project_id)
    await state.set_state(BomCalculatorStates.waiting_screen_type)
    from app.bot.handlers.engineer import BOM_SCREEN_TYPE_PROMPT

    await message.answer(f"Расчёт BOM для проекта «{project.name}».\n{BOM_SCREEN_TYPE_PROMPT}")


@router.message(Command("project_check_stock"))
async def cmd_project_check_stock(message: Message, command: CommandObject) -> None:
    project_id = await _resolve_project_id(message, command, PROJECT_ID_USAGE.format(command="/project_check_stock"))
    if project_id is None:
        return

    async with async_session_maker() as session:
        project = await session.get(Project, project_id)
        if project is None:
            await message.answer(f"Проект #{project_id} не найден.")
            return
        if not project.bom_data:
            await message.answer(NO_BOM_REPLY.format(project_id=project_id))
            return

        deficits = await check_bom_against_stock(session, project.bom_data)

    await message.answer(f"Сверка BOM «{project.name}» со складом:\n{format_deficits(deficits)}")


@router.message(Command("project_pick_list"))
async def cmd_project_pick_list(message: Message, command: CommandObject) -> None:
    project_id = await _resolve_project_id(message, command, PROJECT_ID_USAGE.format(command="/project_pick_list"))
    if project_id is None:
        return

    async with async_session_maker() as session:
        project = await session.get(Project, project_id)
        if project is None:
            await message.answer(f"Проект #{project_id} не найден.")
            return
        if not project.bom_data:
            await message.answer(NO_BOM_REPLY.format(project_id=project_id))
            return

        pick_list = await build_pick_list(session, project.bom_data)

    await message.answer(f"Ведомость выдачи «{project.name}»:\n\n{pick_list}")
