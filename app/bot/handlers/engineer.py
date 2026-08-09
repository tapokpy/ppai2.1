from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.fsm.calculators import ModuleCalculatorStates, PowerCalculatorStates
from app.bot.keyboards.reply import BTN_MODULE_CALC, BTN_POWER_CALC
from app.core.database import async_session_maker
from app.services.business_rules import BusinessRulesEngine, RuleViolation
from app.services.calculators.modules import calculate_modules
from app.services.calculators.power_cables import calculate_power_and_cables

router = Router(name="engineer")


def _format_violations(violations: list[RuleViolation]) -> str:
    if not violations:
        return ""
    return "\n\n⚠️ Предупреждения:\n" + "\n".join(f"— {v.rule_text}" for v in violations)


def _parse_float(text: str) -> float:
    return float(text.replace(",", "."))


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
async def module_pixel_pitch_entered(message: Message, state: FSMContext) -> None:
    try:
        pixel_pitch = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 2.5")
        return

    data = await state.get_data()
    await state.clear()

    result = calculate_modules(width_m=data["width"], height_m=data["height"], pixel_pitch_mm=pixel_pitch)

    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate(
            {"pixel_pitch": pixel_pitch, "width_m": data["width"], "height_m": data["height"]}
        )

    text = (
        f"Модулей: {result.total_modules} ({result.columns}×{result.rows})\n"
        f"Разрешение: {result.resolution_width_px}×{result.resolution_height_px} px\n"
        f"Площадь: {result.area_m2} м²"
    ) + _format_violations(violations)

    await message.answer(text)


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
async def power_module_power_entered(message: Message, state: FSMContext) -> None:
    try:
        module_power_w = _parse_float(message.text)
    except ValueError:
        await message.answer("Введите число, например: 150")
        return

    data = await state.get_data()
    await state.clear()

    result = calculate_power_and_cables(module_count=data["module_count"], module_power_w=module_power_w)

    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate(
            {"module_count": data["module_count"], "module_power_w": module_power_w}
        )

    text = (
        f"Суммарная мощность (с запасом {int(result.power_reserve * 100)}%): {result.total_power_kw} кВт\n"
        f"Номинал автомата: {result.breaker_rating_a} А\n"
        f"Сечение кабеля: {result.cable_cross_section_mm2} мм²\n"
        f"Количество БП: {result.psu_count}"
    ) + _format_violations(violations)

    await message.answer(text)
