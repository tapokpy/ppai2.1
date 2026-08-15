from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.calculators.power_cables import calculate_power_and_cables


async def run(module_count: int, module_power_w: float) -> ToolResult:
    try:
        result = calculate_power_and_cables(module_count=int(module_count), module_power_w=float(module_power_w))
    except (ValueError, TypeError) as exc:
        return ToolResult(text=str(exc), success=False, error=str(exc))

    text = (
        f"Суммарная мощность (с запасом {int(result.power_reserve * 100)}%): {result.total_power_kw} кВт\n"
        f"Номинал автомата: {result.breaker_rating_a} А\n"
        f"Сечение кабеля: {result.cable_cross_section_mm2} мм²\n"
        f"Количество БП: {result.psu_count}"
    )
    items = [
        {"name": "Блок питания", "quantity": result.psu_count, "unit": "шт", "price": ""},
        {"name": f"Автоматический выключатель {result.breaker_rating_a} А", "quantity": 1, "unit": "шт", "price": ""},
        {"name": f"Кабель, сечение {result.cable_cross_section_mm2} мм²", "quantity": 1, "unit": "компл", "price": ""},
    ]
    rows = [{"name": item["name"], "quantity": item["quantity"], "unit_price": 0} for item in items]
    structured_data = {
        "kind": "power_calculation",
        "title": "Смета: питание и кабельная продукция",
        "items": items,
        "rows": rows,
    }
    return ToolResult(text=text, structured_data=structured_data)


TOOL_SPEC = ToolSpec(
    name="calculate_power",
    description=(
        "Считает мощность, номинал автомата, сечение кабеля и количество блоков питания "
        "для LED-экрана по количеству модулей и мощности одного модуля."
    ),
    parameters=[
        ToolParameter(name="module_count", type="integer", description="Количество модулей"),
        ToolParameter(name="module_power_w", type="number", description="Потребление одного модуля в ваттах"),
    ],
    handler=run,
)
