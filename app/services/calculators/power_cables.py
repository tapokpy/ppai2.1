import math
from dataclasses import dataclass

# Standard circuit breaker ratings (A).
STANDARD_BREAKER_RATINGS_A = (6, 10, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160)

# Simplified copper cable ampacity reference (cross-section mm^2 -> max current A).
CABLE_AMPACITY_TABLE_MM2_TO_A = (
    (1.5, 19),
    (2.5, 27),
    (4.0, 38),
    (6.0, 46),
    (10.0, 70),
    (16.0, 85),
    (25.0, 115),
    (35.0, 135),
)

BREAKER_SAFETY_MARGIN = 1.25


@dataclass
class PowerCalculationResult:
    total_power_kw: float
    breaker_rating_a: int
    cable_cross_section_mm2: float
    psu_count: int
    power_reserve: float


def calculate_power_and_cables(
    module_count: int,
    module_power_w: float,
    psu_power_w: float = 200.0,
    voltage_v: float = 220.0,
    power_reserve: float = 0.2,
) -> PowerCalculationResult:
    if module_count <= 0:
        raise ValueError("Количество модулей должно быть положительным")
    if module_power_w <= 0:
        raise ValueError("Потребление модуля должно быть положительным")
    if psu_power_w <= 0:
        raise ValueError("Мощность блока питания должна быть положительной")

    total_power_w = module_count * module_power_w * (1 + power_reserve)
    total_current_a = total_power_w / voltage_v

    breaker_rating_a = _select_breaker_rating(total_current_a * BREAKER_SAFETY_MARGIN)
    cable_cross_section_mm2 = _select_cable_cross_section(breaker_rating_a)
    psu_count = math.ceil(total_power_w / psu_power_w)

    return PowerCalculationResult(
        total_power_kw=round(total_power_w / 1000, 3),
        breaker_rating_a=breaker_rating_a,
        cable_cross_section_mm2=cable_cross_section_mm2,
        psu_count=psu_count,
        power_reserve=power_reserve,
    )


def _select_breaker_rating(required_current_a: float) -> int:
    for rating in STANDARD_BREAKER_RATINGS_A:
        if rating >= required_current_a:
            return rating
    return STANDARD_BREAKER_RATINGS_A[-1]


def _select_cable_cross_section(breaker_rating_a: int) -> float:
    for cross_section, ampacity in CABLE_AMPACITY_TABLE_MM2_TO_A:
        if ampacity >= breaker_rating_a:
            return cross_section
    return CABLE_AMPACITY_TABLE_MM2_TO_A[-1][0]
