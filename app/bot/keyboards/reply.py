from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_POWER_CALC = "🔌 Расчёт потребления и кабелей"
BTN_MODULE_CALC = "🧮 Расчёт количества модулей"
BTN_BOM_CALC = "📐 Полный BOM-расчёт (золотой стандарт)"
BTN_STOCK_SUMMARY = "📦 Сводка по складу"
BTN_COMPONENTS = "🧩 Подбор комплектующих"
BTN_RAG_MEMORY = "🧠 RAG и память"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_POWER_CALC), KeyboardButton(text=BTN_MODULE_CALC)],
            [KeyboardButton(text=BTN_BOM_CALC)],
            [KeyboardButton(text=BTN_STOCK_SUMMARY), KeyboardButton(text=BTN_COMPONENTS)],
            [KeyboardButton(text=BTN_RAG_MEMORY)],
        ],
        resize_keyboard=True,
    )
