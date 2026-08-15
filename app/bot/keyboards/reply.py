from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

# Calculators (module/power/BOM) were removed from this menu — they're the
# only three commands in the whole bot that had NO trigger besides an exact
# button-text match, so they moved to slash commands (/calc_modules,
# /calc_power, /calc_bom in app/bot/handlers/engineer.py) instead, keeping
# them reachable without cluttering the menu with less-frequently-used
# buttons. "Подбор комплектующих" (BTN_COMPONENTS) is gone entirely — it
# never had a handler wired to it.
BTN_STOCK_SUMMARY = "📦 Сводка по складу"
BTN_STOCK_ADD = "➕ Добавить остаток"
BTN_TODO_LIST = "✅ Список моих задач"
BTN_MY_PROJECTS = "📁 Мои проекты"
BTN_RAG_MEMORY = "🧠 RAG и память"
BTN_DASHBOARD = "🔑 Дашборд"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STOCK_SUMMARY), KeyboardButton(text=BTN_STOCK_ADD)],
            [KeyboardButton(text=BTN_TODO_LIST), KeyboardButton(text=BTN_MY_PROJECTS)],
            [KeyboardButton(text=BTN_RAG_MEMORY), KeyboardButton(text=BTN_DASHBOARD)],
        ],
        resize_keyboard=True,
    )
