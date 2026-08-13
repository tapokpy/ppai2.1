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


class PromptType(str, Enum):
    DEFAULT = "default"
    SALES = "sales"
    CALCULATOR = "calculator"


_RULES = (
    "1. Отвечай только на основе фактов из контекста ниже (если он дан) или из "
    "точно известной информации.\n"
    "2. Если сомневаешься в конкретных цифрах, характеристиках, ценах или "
    "названиях — прямо скажи, что не уверен, вместо того чтобы придумывать "
    "правдоподобное значение.\n"
    "3. Если информации недостаточно для ответа, попроси уточнить вопрос."
)

SYSTEM_PROMPTS: dict[PromptType, str] = {
    PromptType.DEFAULT: f"Ты инженерный ИИ-ассистент. Правила:\n{_RULES}",
    PromptType.SALES: (
        "Ты ассистент по продажам светодиодных экранов. Правила:\n"
        f"{_RULES}\n"
        "4. Не завышай характеристики оборудования сверх того, что указано в контексте."
    ),
    PromptType.CALCULATOR: (
        "Ты инженерный калькулятор. Правила:\n"
        f"{_RULES}\n"
        "4. Показывай, как получен результат (входные данные -> формула -> результат)."
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
