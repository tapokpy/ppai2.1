from app.core.tool_registry import ToolParameter, ToolResult, ToolSpec
from app.services.calculators.modules import calculate_modules


async def run(width_m: float, height_m: float, pixel_pitch_mm: float) -> ToolResult:
    try:
        result = calculate_modules(
            width_m=float(width_m), height_m=float(height_m), pixel_pitch_mm=float(pixel_pitch_mm)
        )
    except (ValueError, TypeError) as exc:
        return ToolResult(text=str(exc), success=False, error=str(exc))

    text = (
        f"Модулей: {result.total_modules} ({result.columns}×{result.rows})\n"
        f"Разрешение: {result.resolution_width_px}×{result.resolution_height_px} px\n"
        f"Площадь: {result.area_m2} м²"
    )
    return ToolResult(text=text)


TOOL_SPEC = ToolSpec(
    name="calculate_modules",
    description=(
        "Считает количество модулей, разрешение и площадь для LED-экрана по ширине, высоте "
        "(в метрах) и шагу пикселя (в мм)."
    ),
    parameters=[
        ToolParameter(name="width_m", type="number", description="Ширина экрана в метрах"),
        ToolParameter(name="height_m", type="number", description="Высота экрана в метрах"),
        ToolParameter(name="pixel_pitch_mm", type="number", description="Шаг пикселя в миллиметрах"),
    ],
    handler=run,
)
