import math
from dataclasses import dataclass

# Cabinet sizes per LED_Master_Knowledge_Base.md section 2 — these are the
# smallest deployable, non-cuttable structural units for Fixed/Rental
# installs (запрет на подрезку модулей). The doc's PSU limits ("Outdoor SV
# 400W: макс 7 модулей") are read as "7 cabinets" here: this file treats
# cabinet == the top-level countable unit for PSU/port/card/ZIP purposes,
# since the doc gives no separate cabinet-vs-module subdivision ratio —
# there's nothing in the source to size a finer breakdown from.
CABINET_SIZES_MM: dict[str, tuple[float, float]] = {
    "outdoor": (960.0, 960.0),
    "outdoor_compact": (440.0, 440.0),
    "indoor": (640.0, 640.0),
    "rental": (250.0, 250.0),
}
SCREEN_TYPES_WITH_FIXED_CABINET = tuple(CABINET_SIZES_MM)
OPEN_FRAME = "open_frame"
ALL_SCREEN_TYPES = SCREEN_TYPES_WITH_FIXED_CABINET + (OPEN_FRAME,)

# Open Frame has no cabinet size in the doc at all — it's explicitly "for
# modules with pitch > P2" (i.e. pixel pitch above 2mm), tiled directly by
# module_size_mm the caller supplies.
OPEN_FRAME_MIN_PIXEL_PITCH_MM = 2.0


@dataclass
class PsuSpec:
    power_w: float
    max_units_per_psu: int | None  # None = no documented per-unit cap, size by wattage only


# Only outdoor/indoor have a documented PSU model+cap in the knowledge
# base. Rental/Open Frame aren't specified there, so callers must pass
# psu_power_w explicitly for those types instead of getting a silently
# invented default.
PSU_SPECS: dict[str, PsuSpec] = {
    "outdoor": PsuSpec(power_w=400.0, max_units_per_psu=7),
    "outdoor_compact": PsuSpec(power_w=400.0, max_units_per_psu=7),
    "indoor": PsuSpec(power_w=300.0, max_units_per_psu=10),
}

POWER_MARGIN_FACTOR = 1.3  # +30%, mandatory per golden standard
AVERAGE_POWER_LOW_FRACTION = 0.20
AVERAGE_POWER_HIGH_FRACTION = 0.30
VOLTAGE_380_THRESHOLD_W = 15_000.0
PORT_CAPACITY_PX = 650_000
ZIP_MODULES_FRACTION = 0.05
ZIP_PSU_FRACTION = 0.03
ZIP_CARDS_FRACTION = 0.03


class LedBomError(ValueError):
    pass


@dataclass
class LedBomResult:
    screen_type: str
    unit_count: int
    columns: int
    rows: int
    resolution_width_px: int
    resolution_height_px: int
    total_pixels: int
    peak_power_kw: float
    peak_power_with_margin_kw: float
    average_power_kw_low: float
    average_power_kw_high: float
    voltage_v: int
    psu_count: int
    psu_power_w: float
    card_count: int
    port_count: int
    zip_modules: int
    zip_psu: int
    zip_cards: int

    def to_rows(self) -> list[dict]:
        return [
            {"name": "Кабинет/модуль", "quantity": self.unit_count, "unit": "шт"},
            {"name": "ЗИП: модули (5%)", "quantity": self.zip_modules, "unit": "шт"},
            {"name": "Блок питания", "quantity": self.psu_count, "unit": "шт"},
            {"name": "ЗИП: блоки питания (3%)", "quantity": self.zip_psu, "unit": "шт"},
            {"name": "Приёмная карта", "quantity": self.card_count, "unit": "шт"},
            {"name": "ЗИП: приёмные карты (3%)", "quantity": self.zip_cards, "unit": "шт"},
            {"name": "Порты контроллера", "quantity": self.port_count, "unit": "шт"},
        ]


def calculate_bom(
    width_mm: float,
    height_mm: float,
    pixel_pitch_mm: float,
    screen_type: str,
    module_power_w: float,
    module_size_mm: float | None = None,
    psu_power_w: float | None = None,
) -> LedBomResult:
    if width_mm <= 0 or height_mm <= 0:
        raise LedBomError("Ширина и высота экрана должны быть положительными")
    if pixel_pitch_mm <= 0:
        raise LedBomError("Шаг пикселя должен быть положительным")
    if module_power_w <= 0:
        raise LedBomError("Потребление модуля должно быть положительным")
    if screen_type not in ALL_SCREEN_TYPES:
        raise LedBomError(f"Неизвестный тип экрана «{screen_type}». Доступны: {', '.join(ALL_SCREEN_TYPES)}")

    if screen_type == OPEN_FRAME:
        if pixel_pitch_mm <= OPEN_FRAME_MIN_PIXEL_PITCH_MM:
            raise LedBomError(
                f"Open Frame применим только при шаге пикселя больше {OPEN_FRAME_MIN_PIXEL_PITCH_MM} мм (P2)."
            )
        if not module_size_mm or module_size_mm <= 0:
            raise LedBomError("Для Open Frame нужно указать размер модуля (module_size_mm).")
        unit_w_mm, unit_h_mm = module_size_mm, module_size_mm
    else:
        unit_w_mm, unit_h_mm = CABINET_SIZES_MM[screen_type]

    columns = math.ceil(width_mm / unit_w_mm)
    rows = math.ceil(height_mm / unit_h_mm)
    unit_count = columns * rows

    pixels_per_unit_side = round(unit_w_mm / pixel_pitch_mm)
    resolution_width_px = columns * pixels_per_unit_side
    resolution_height_px = rows * pixels_per_unit_side
    total_pixels = resolution_width_px * resolution_height_px

    peak_power_w = unit_count * module_power_w
    peak_power_with_margin_w = peak_power_w * POWER_MARGIN_FACTOR
    voltage_v = 380 if peak_power_with_margin_w >= VOLTAGE_380_THRESHOLD_W else 220

    psu_spec = PSU_SPECS.get(screen_type)
    if psu_spec is not None:
        resolved_psu_power_w = psu_power_w or psu_spec.power_w
        max_units_per_psu = psu_spec.max_units_per_psu
    else:
        if not psu_power_w or psu_power_w <= 0:
            raise LedBomError(
                f"Для типа «{screen_type}» нет табличного БП в базе знаний — укажите psu_power_w явно."
            )
        resolved_psu_power_w = psu_power_w
        max_units_per_psu = None

    psu_count_by_power = math.ceil(peak_power_with_margin_w / resolved_psu_power_w)
    psu_count_by_units = math.ceil(unit_count / max_units_per_psu) if max_units_per_psu else 0
    psu_count = max(psu_count_by_power, psu_count_by_units)

    card_count = unit_count  # 1 receiving card per cabinet (baseline)
    port_count = math.ceil(total_pixels / PORT_CAPACITY_PX)

    return LedBomResult(
        screen_type=screen_type,
        unit_count=unit_count,
        columns=columns,
        rows=rows,
        resolution_width_px=resolution_width_px,
        resolution_height_px=resolution_height_px,
        total_pixels=total_pixels,
        peak_power_kw=round(peak_power_w / 1000, 3),
        peak_power_with_margin_kw=round(peak_power_with_margin_w / 1000, 3),
        average_power_kw_low=round(peak_power_w * AVERAGE_POWER_LOW_FRACTION / 1000, 3),
        average_power_kw_high=round(peak_power_w * AVERAGE_POWER_HIGH_FRACTION / 1000, 3),
        voltage_v=voltage_v,
        psu_count=psu_count,
        psu_power_w=resolved_psu_power_w,
        card_count=card_count,
        port_count=port_count,
        zip_modules=math.ceil(unit_count * ZIP_MODULES_FRACTION),
        zip_psu=math.ceil(psu_count * ZIP_PSU_FRACTION),
        zip_cards=math.ceil(card_count * ZIP_CARDS_FRACTION),
    )
