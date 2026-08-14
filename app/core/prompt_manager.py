from enum import Enum

from app.core.capabilities import load_capabilities_summary
from app.core.config import settings
from app.core.led_golden_standard import GOLDEN_STANDARD_TEXT

CALCULATOR_KEYWORDS = (
    "рассчитай",
    "посчитай",
    "расчёт",
    "расчет",
    "формула",
    "мощность",
    "сечение",
    "ампер",
    "автомат",
)
SALES_KEYWORDS = (
    "цена",
    "стоимость",
    "заказать",
    "купить",
    "предложение",
    "комплект",
    "подберите",
    "коммерческое",
)
# "Умеешь ли ты работать с чертежами?" style meta-questions about Loki's own
# toolset — answered from capabilities.yaml (see _RULES rule 2), not RAG.
# Checked before the RAG query even runs (app/core/router.py) — RAG finding
# some tangentially-related project-doc chunk for a capability question was
# observed live to confuse the local model into a degenerate/non-Russian
# response instead of just listing what it can do.
CAPABILITY_QUESTION_KEYWORDS = (
    "умеешь",
    "можешь ли ты",
    "что ты умеешь",
    "что ты можешь",
    "твои возможности",
    "функционал",
    "какие у тебя функции",
    "с чем ты работаешь",
    "какие форматы ты",
    "какие команды",
)


def is_capability_question(query: str) -> bool:
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in CAPABILITY_QUESTION_KEYWORDS)


class PromptType(str, Enum):
    DEFAULT = "default"
    SALES = "sales"
    CALCULATOR = "calculator"


_RULES = (
    "1. Отвечай ВСЕГДА на русском языке — независимо от языка вопроса, найденного "
    "контекста или содержимого файлов. Никогда не переключайся на другой язык, "
    "даже частично.\n"
    "2. Если вопрос про твои возможности (\"умеешь ли ты...\", \"можешь ли ты...\", "
    "\"что ты умеешь\") — отвечай по перечню твоих функций, приведённому в этом "
    "системном промпте, полно и конкретно (что именно делаешь, с какими "
    "форматами/командами). Раздел «Контекст» (если есть) для таких вопросов не "
    "главный источник — он для фактических вопросов по документации и базе "
    "знаний, а не для описания твоих функций.\n"
    "3. Для остальных вопросов отвечай только на основе фактов из контекста ниже "
    "(если он дан) или из точно известной информации.\n"
    "4. Если сомневаешься в конкретных цифрах, характеристиках, ценах или "
    "названиях — прямо скажи, что не уверен, вместо того чтобы придумывать "
    "правдоподобное значение.\n"
    "5. Если информации недостаточно для ответа, попроси уточнить вопрос."
)

SYSTEM_PROMPTS: dict[PromptType, str] = {
    PromptType.DEFAULT: f"Ты инженерный ИИ-ассистент. Правила:\n{_RULES}",
    PromptType.SALES: (
        "Ты ассистент по продажам светодиодных экранов. Правила:\n"
        f"{_RULES}\n"
        "6. Не завышай характеристики оборудования сверх того, что указано в контексте."
    ),
    PromptType.CALCULATOR: (
        "Ты инженерный калькулятор. Правила:\n"
        f"{_RULES}\n"
        "6. Показывай, как получен результат (входные данные -> формула -> результат)."
    ),
}

# Appended only to the main cascade's answer-generation calls (not to
# reminder/todo parsing or KB-summary calls, which need their own strict
# output formats). A single self-reported confidence marker instead of
# regenerating the answer multiple times to check consistency — cheap (one
# extra sentence, not extra LLM calls) and lets the router escalate
# low-confidence local answers to Cloud the same way it already escalates on
# [NEED_CLOUD].
CONFIDENCE_INSTRUCTION = (
    "\n\nВ конце ответа, на отдельной строке, укажи свою уверенность в ответе "
    "строго в формате [CONFIDENCE: high], [CONFIDENCE: medium] или "
    "[CONFIDENCE: low]. Ставь low, если отвечаешь по памяти без контекста "
    "или не уверен в конкретных цифрах/фактах."
)


def get_system_prompt(prompt_type: PromptType = PromptType.DEFAULT) -> str:
    parts = [SYSTEM_PROMPTS.get(prompt_type, SYSTEM_PROMPTS[PromptType.DEFAULT])]

    capabilities = load_capabilities_summary(settings.CAPABILITIES_PATH)
    if capabilities:
        parts.append(capabilities)

    # Unconditional (not just for PromptType.CALCULATOR) — these rules must
    # hold for any answer that touches equipment/BOM, including casual
    # sales/default-prompt conversation, not just explicit calculator flows.
    parts.append(GOLDEN_STANDARD_TEXT)

    return "\n\n".join(parts)


def detect_prompt_type(query: str) -> PromptType:
    query_lower = query.lower()

    if any(keyword in query_lower for keyword in CALCULATOR_KEYWORDS):
        return PromptType.CALCULATOR

    if any(keyword in query_lower for keyword in SALES_KEYWORDS):
        return PromptType.SALES

    return PromptType.DEFAULT
