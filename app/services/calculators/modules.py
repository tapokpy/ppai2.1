import math
from dataclasses import dataclass


@dataclass
class ModuleCalculationResult:
    columns: int
    rows: int
    total_modules: int
    resolution_width_px: int
    resolution_height_px: int
    area_m2: float


def calculate_modules(
    width_m: float,
    height_m: float,
    pixel_pitch_mm: float,
    module_size_m: float = 0.5,
) -> ModuleCalculationResult:
    if width_m <= 0 or height_m <= 0:
        raise ValueError("Ширина и высота экрана должны быть положительными")
    if pixel_pitch_mm <= 0:
        raise ValueError("Шаг пикселя должен быть положительным")
    if module_size_m <= 0:
        raise ValueError("Размер модуля должен быть положительным")

    columns = math.ceil(width_m / module_size_m)
    rows = math.ceil(height_m / module_size_m)
    total_modules = columns * rows

    pixels_per_module_side = round(module_size_m * 1000 / pixel_pitch_mm)
    resolution_width_px = columns * pixels_per_module_side
    resolution_height_px = rows * pixels_per_module_side

    area_m2 = round(columns * module_size_m * rows * module_size_m, 3)

    return ModuleCalculationResult(
        columns=columns,
        rows=rows,
        total_modules=total_modules,
        resolution_width_px=resolution_width_px,
        resolution_height_px=resolution_height_px,
        area_m2=area_m2,
    )
