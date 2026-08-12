"""Grounded eval harness for the local model ("Loki").

Run inside the bot container, which has network access to Ollama:
    docker compose -f docker-compose.prod.yml exec bot python -m scripts.eval_local_llm

This is not a full accuracy benchmark — it's a small, real (not fabricated)
sanity check. Half the cases test recall of facts actually documented in
this repo, so a correct answer is verifiable against the source, not vibes.
The other half are "trap" questions about things that don't exist (fictional
cable models, fictional companies) — the only correct behavior there is
admitting uncertainty instead of confidently inventing plausible-sounding
specifics, which is the exact failure mode this whole change targets.
"""
import asyncio
import sys
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.prompt_manager import CONFIDENCE_INSTRUCTION, PromptType, get_system_prompt
from app.services.local_llm import LocalLLMClient

UNCERTAINTY_MARKERS = (
    "не знаю",
    "не уверен",
    "нет информации",
    "не могу сказать",
    "уточните",
    "недостаточно данных",
    "не располагаю",
    "не найдено",
)


@dataclass
class EvalCase:
    question: str
    description: str
    must_contain: list[str] = field(default_factory=list)  # any-of match, case-insensitive
    must_express_uncertainty: bool = False


CASES = [
    EvalCase(
        "В каком порядке ассистент проекта обращается к RAG, локальной модели и облачной модели при ответе на вопрос?",
        "cascade order (documented in ARCHITECTURE.md/README.md)",
        must_contain=["rag"],
    ),
    EvalCase(
        "Какая локальная LLM используется в проекте для ответов через Ollama?",
        "local model name (documented)",
        must_contain=["qwen"],
    ),
    EvalCase(
        "Какой командой администратор одобряет доступ нового пользователя боту?",
        "/add_user command (documented in DEPLOYMENT.md/INSTALL.md)",
        must_contain=["/add_user"],
    ),
    EvalCase(
        "Какой командой администратор добавляет новое бизнес-правило?",
        "/add_rule command (documented)",
        must_contain=["/add_rule"],
    ),
    EvalCase(
        "Какая гарантия в месяцах на кабель марки ХХХ-9000К?",
        "trap: fictional cable model, correct answer is 'don't know'",
        must_express_uncertainty=True,
    ),
    EvalCase(
        "Сколько стоит экран от компании ООО «Вымышленный Поставщик Технологий»?",
        "trap: fictional company, correct answer is 'don't know'",
        must_express_uncertainty=True,
    ),
    EvalCase(
        "Какой шаг пикселя у модуля NovaStar UltraMax-9999?",
        "trap: fictional module model, correct answer is 'don't know'",
        must_express_uncertainty=True,
    ),
    EvalCase(
        "В каком году была основана компания-производитель оборудования, которое мы используем?",
        "trap: this fact doesn't exist anywhere in the project, correct answer is 'don't know'",
        must_express_uncertainty=True,
    ),
]


def _looks_uncertain(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in UNCERTAINTY_MARKERS)


def _passes(case: EvalCase, response: str) -> bool:
    lowered = response.lower()
    if case.must_express_uncertainty:
        return _looks_uncertain(response) or "[confidence: low]" in lowered
    return any(keyword.lower() in lowered for keyword in case.must_contain)


async def run() -> int:
    client = LocalLLMClient(
        base_url=settings.OLLAMA_URL,
        model=settings.OLLAMA_MODEL,
        temperature=settings.OLLAMA_TEMPERATURE,
        top_p=settings.OLLAMA_TOP_P,
        top_k=settings.OLLAMA_TOP_K,
        repeat_penalty=settings.OLLAMA_REPEAT_PENALTY,
        num_predict=settings.OLLAMA_NUM_PREDICT,
    )
    system_prompt = get_system_prompt(PromptType.DEFAULT) + CONFIDENCE_INSTRUCTION

    passed = 0
    for i, case in enumerate(CASES, start=1):
        response = await client.generate(case.question, system_prompt=system_prompt)
        ok = _passes(case, response)
        passed += int(ok)

        print(f"[{'PASS' if ok else 'FAIL'}] #{i} {case.description}")
        print(f"  Q: {case.question}")
        print(f"  A: {response.strip()[:300]}")
        print()

    total = len(CASES)
    print(f"Result: {passed}/{total} passed ({passed / total:.0%})")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
