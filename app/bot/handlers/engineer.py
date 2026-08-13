from dataclasses import asdict

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.fsm.calculators import BomCalculatorStates, ModuleCalculatorStates, PowerCalculatorStates
from app.bot.keyboards.reply import BTN_BOM_CALC, BTN_MODULE_CALC, BTN_POWER_CALC
from app.bot.keyboards.inline import calculator_export_actions
from app.core.database import async_session_maker
from app.models.sqlalchemy.message import Message as MessageModel
from app.models.sqlalchemy.project import Project
from app.models.sqlalchemy.user import User
from app.services.audit import log_action
from app.services.bom_reconciliation import check_bom_against_stock, format_deficits
from app.services.business_rules import BusinessRulesEngine, RuleViolation
from app.services.calculators.led_bom import (
    ALL_SCREEN_TYPES,
    OPEN_FRAME,
    PSU_SPECS,
    LedBomError,
    LedBomResult,
    calculate_bom,
)
from app.services.calculators.modules import ModuleCalculationResult, calculate_modules
from app.services.calculators.power_cables import PowerCalculationResult, calculate_power_and_cables

router = Router(name="engineer")


def _format_violations(violations: list[RuleViolation]) -> str:
    if not violations:
        return ""
    return "\n\n⚠️ Предупреждения:\n" + "\n".join(f"— {v.rule_text}" for v in violations)


def _parse_float(text: str) -> float:
    return float(text.replace(",", "."))


def _module_result_to_structured_data(result: ModuleCalculationResult, pixel_pitch: float) -> dict:
    item_name = f"Модуль дисплея, шаг пикселя {pixel_pitch} мм"
    return {
        "kind": "module_calculation",
        "title": "Коммерческое предложение: модульный экран",
        "items": [{"name": item_name, "quantity": result.total_modules, "unit": "шт", "price": ""}],
        "rows": [{"name": item_name, "quantity": result.total_modules, "unit_price": 0}],
    }


def _power_result_to_structured_data(result: PowerCalculationResult) -> dict:
    items = [
        {"name": "Блок питания", "quantity": result.psu_count, "unit": "шт", "price": ""},
        {
            "name": f"Автоматический выключатель {result.breaker_rating_a} А",
            "quantity": 1,
            "unit": "шт",
            "price": "",
        },
        {
            "name": f"Кабель, сечение {result.cable_cross_section_mm2} мм²",
            "quantity": 1,
            "unit": "компл",
            "price": "",
        },
    ]
    rows = [{"name": item["name"], "quantity": item["quantity"], "unit_price": 0} for item in items]
    return {"kind": "power_calculation", "title": "Смета: питание и кабельная продукция", "items": items, "rows": rows}


async def _save_calculator_result(
    message: Message, db_user: User, prompt: str, response_text: str, structured_data: dict
) -> None:
    async with async_session_maker() as session:
        session.add(
            MessageModel(
                user_id=db_user.id,
                telegram_message_id=message.message_id,
                prompt=prompt,
                response=response_text,
                source="calculator",
                context_used=False,
                structured_data=structured_data,
            )
        )
        await session.commit()


@router.message(F.text == BTN_MODULE_CALC)
async def start_module_calculator(message: Message, state: FSMContext) -> None:
    await state.set_state(ModuleCalculatorStates.waiting_width)
    await message.answer("Введите ширину экрана в метрах:")


@router.message(StateFilter(ModuleCalculatorStates.waiting_width))
async def module_width_entered(message: Message, state: FSMContext) -> None:
    try:
        width = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 3.5")
        return

    await state.update_data(width=width)
    await state.set_state(ModuleCalculatorStates.waiting_height)
    await message.answer("Введите высоту экрана в метрах:")


@router.message(StateFilter(ModuleCalculatorStates.waiting_height))
async def module_height_entered(message: Message, state: FSMContext) -> None:
    try:
        height = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 2.0")
        return

    await state.update_data(height=height)
    await state.set_state(ModuleCalculatorStates.waiting_pixel_pitch)
    await message.answer("Введите шаг пикселя в мм (например, 2.5):")


@router.message(StateFilter(ModuleCalculatorStates.waiting_pixel_pitch))
async def module_pixel_pitch_entered(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        pixel_pitch = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 2.5")
        return

    data = await state.get_data()
    await state.clear()

    result = calculate_modules(width_m=data["width"], height_m=data["height"], pixel_pitch_mm=pixel_pitch)

    calc_context = {"pixel_pitch": pixel_pitch, "width_m": data["width"], "height_m": data["height"]}
    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate(calc_context)

    text = (
        f"Модулей: {result.total_modules} ({result.columns}×{result.rows})\n"
        f"Разрешение: {result.resolution_width_px}×{result.resolution_height_px} px\n"
        f"Площадь: {result.area_m2} м²"
    ) + _format_violations(violations)

    await _save_calculator_result(
        message,
        db_user,
        prompt=f"Расчёт модулей: {data['width']}×{data['height']} м, шаг {pixel_pitch} мм",
        response_text=text,
        structured_data=_module_result_to_structured_data(result, pixel_pitch),
    )
    await message.answer(text, reply_markup=calculator_export_actions(message.message_id))


@router.message(F.text == BTN_POWER_CALC)
async def start_power_calculator(message: Message, state: FSMContext) -> None:
    await state.set_state(PowerCalculatorStates.waiting_module_count)
    await message.answer("Введите количество модулей:")


@router.message(StateFilter(PowerCalculatorStates.waiting_module_count))
async def power_module_count_entered(message: Message, state: FSMContext) -> None:
    try:
        module_count = int(message.text)
    except ValueError:
        await message.answer("Введите целое число, например: 48")
        return

    await state.update_data(module_count=module_count)
    await state.set_state(PowerCalculatorStates.waiting_module_power)
    await message.answer("Введите потребление одного модуля в ваттах (например, 150):")


@router.message(StateFilter(PowerCalculatorStates.waiting_module_power))
async def power_module_power_entered(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        module_power_w = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 150")
        return

    data = await state.get_data()
    await state.clear()

    result = calculate_power_and_cables(module_count=data["module_count"], module_power_w=module_power_w)

    calc_context = {"module_count": data["module_count"], "module_power_w": module_power_w}
    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate(calc_context)

    text = (
        f"Суммарная мощность (с запасом {int(result.power_reserve * 100)}%): {result.total_power_kw} кВт\n"
        f"Номинал автомата: {result.breaker_rating_a} А\n"
        f"Сечение кабеля: {result.cable_cross_section_mm2} мм²\n"
        f"Количество БП: {result.psu_count}"
    ) + _format_violations(violations)

    await _save_calculator_result(
        message,
        db_user,
        prompt=f"Расчёт питания: {data['module_count']} модулей по {module_power_w} Вт",
        response_text=text,
        structured_data=_power_result_to_structured_data(result),
    )
    await message.answer(text, reply_markup=calculator_export_actions(message.message_id))


BOM_SCREEN_TYPE_PROMPT = f"Тип экрана ({', '.join(ALL_SCREEN_TYPES)}):"
BOM_INVALID_SCREEN_TYPE_REPLY = f"Не понял тип экрана. Варианты: {', '.join(ALL_SCREEN_TYPES)}"


def _format_bom_result(result: LedBomResult) -> str:
    return (
        f"Кабинетов/модулей: {result.unit_count} ({result.columns}×{result.rows})\n"
        f"Разрешение: {result.resolution_width_px}×{result.resolution_height_px} px\n"
        f"Пиковая мощность: {result.peak_power_kw} кВт (с запасом +30%: {result.peak_power_with_margin_kw} кВт)\n"
        f"Среднее потребление: {result.average_power_kw_low}–{result.average_power_kw_high} кВт\n"
        f"Питание: {result.voltage_v} В\n"
        f"БП: {result.psu_count} шт ({result.psu_power_w} Вт)\n"
        f"Приёмных карт: {result.card_count}, портов контроллера: {result.port_count}\n"
        f"ЗИП: модули {result.zip_modules}, БП {result.zip_psu}, карты {result.zip_cards}"
    )


def _bom_result_to_structured_data(result: LedBomResult) -> dict:
    rows = result.to_rows()
    items = [{"name": r["name"], "quantity": r["quantity"], "unit": r["unit"], "price": ""} for r in rows]
    structured_rows = [{"name": r["name"], "quantity": r["quantity"], "unit_price": 0} for r in rows]
    return {
        "kind": "led_bom_calculation",
        "title": "Спецификация BOM: LED-экран (золотой стандарт)",
        "items": items,
        "rows": structured_rows,
    }


@router.message(F.text == BTN_BOM_CALC)
async def start_bom_calculator(message: Message, state: FSMContext) -> None:
    await state.set_state(BomCalculatorStates.waiting_screen_type)
    await message.answer(BOM_SCREEN_TYPE_PROMPT)


@router.message(StateFilter(BomCalculatorStates.waiting_screen_type))
async def bom_screen_type_entered(message: Message, state: FSMContext) -> None:
    screen_type = message.text.strip().lower()
    if screen_type not in ALL_SCREEN_TYPES:
        await message.answer(BOM_INVALID_SCREEN_TYPE_REPLY)
        return

    await state.update_data(screen_type=screen_type)
    await state.set_state(BomCalculatorStates.waiting_width)
    await message.answer("Ширина экрана в мм:")


@router.message(StateFilter(BomCalculatorStates.waiting_width))
async def bom_width_entered(message: Message, state: FSMContext) -> None:
    try:
        width_mm = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 3840")
        return

    await state.update_data(width_mm=width_mm)
    await state.set_state(BomCalculatorStates.waiting_height)
    await message.answer("Высота экрана в мм:")


@router.message(StateFilter(BomCalculatorStates.waiting_height))
async def bom_height_entered(message: Message, state: FSMContext) -> None:
    try:
        height_mm = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 2160")
        return

    await state.update_data(height_mm=height_mm)
    await state.set_state(BomCalculatorStates.waiting_pixel_pitch)
    await message.answer("Шаг пикселя в мм:")


@router.message(StateFilter(BomCalculatorStates.waiting_pixel_pitch))
async def bom_pixel_pitch_entered(message: Message, state: FSMContext) -> None:
    try:
        pixel_pitch_mm = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 2.5")
        return

    await state.update_data(pixel_pitch_mm=pixel_pitch_mm)
    await state.set_state(BomCalculatorStates.waiting_module_power)
    await message.answer("Пиковая мощность одного кабинета/модуля в Вт:")


@router.message(StateFilter(BomCalculatorStates.waiting_module_power))
async def bom_module_power_entered(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        module_power_w = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 600")
        return

    await state.update_data(module_power_w=module_power_w)
    data = await state.get_data()
    screen_type = data["screen_type"]

    if screen_type == OPEN_FRAME:
        await state.set_state(BomCalculatorStates.waiting_module_size)
        await message.answer("Размер модуля в мм (сторона квадрата):")
        return

    if screen_type not in PSU_SPECS:
        await state.set_state(BomCalculatorStates.waiting_psu_power)
        await message.answer("Для этого типа нет табличного БП в базе знаний — укажите мощность БП в Вт:")
        return

    await _finish_bom_calculation(message, state, db_user)


@router.message(StateFilter(BomCalculatorStates.waiting_module_size))
async def bom_module_size_entered(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        module_size_mm = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 250")
        return

    await state.update_data(module_size_mm=module_size_mm)
    # Open Frame has no golden-standard PSU table either.
    await state.set_state(BomCalculatorStates.waiting_psu_power)
    await message.answer("Мощность БП в Вт (для Open Frame нет табличного значения):")


@router.message(StateFilter(BomCalculatorStates.waiting_psu_power))
async def bom_psu_power_entered(message: Message, state: FSMContext, db_user: User) -> None:
    try:
        psu_power_w = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 300")
        return

    await state.update_data(psu_power_w=psu_power_w)
    await _finish_bom_calculation(message, state, db_user)


async def _finish_bom_calculation(message: Message, state: FSMContext, db_user: User) -> None:
    data = await state.get_data()
    await state.clear()

    try:
        result = calculate_bom(
            width_mm=data["width_mm"],
            height_mm=data["height_mm"],
            pixel_pitch_mm=data["pixel_pitch_mm"],
            screen_type=data["screen_type"],
            module_power_w=data["module_power_w"],
            module_size_mm=data.get("module_size_mm"),
            psu_power_w=data.get("psu_power_w"),
        )
    except LedBomError as exc:
        await message.answer(str(exc))
        return

    text = _format_bom_result(result)

    project_id = data.get("bom_target_project_id")
    if project_id is not None:
        async with async_session_maker() as session:
            project = await session.get(Project, project_id)
            if project is not None:
                project.bom_data = asdict(result)
                await session.commit()
                await log_action(
                    session,
                    user_id=db_user.id,
                    command_text=f"/project_bom {project_id} -> {data['screen_type']}",
                    module="projects",
                    decision="bom_saved",
                    detail={"project_id": project.id, "unit_count": result.unit_count},
                )

                deficits = await check_bom_against_stock(session, project.bom_data)
                text += f"\n\nСохранено в проект «{project.name}».\n\nОстатки на складе:\n{format_deficits(deficits)}"

    await _save_calculator_result(
        message,
        db_user,
        prompt=f"BOM-расчёт: {data['width_mm']}×{data['height_mm']} мм, {data['screen_type']}",
        response_text=text,
        structured_data=_bom_result_to_structured_data(result),
    )
    await message.answer(text, reply_markup=calculator_export_actions(message.message_id))
