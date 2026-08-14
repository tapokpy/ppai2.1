from unittest.mock import patch

import pytest

from app.core.capabilities import load_capabilities_summary
from app.core.prompt_manager import PromptType, detect_prompt_type, get_system_prompt, is_capability_question


def test_detects_calculator_type():
    assert detect_prompt_type("рассчитай мощность экрана") == PromptType.CALCULATOR
    assert detect_prompt_type("какое сечение кабеля нужно для 30А?") == PromptType.CALCULATOR


def test_detects_sales_type():
    assert detect_prompt_type("сколько стоит комплект оборудования?") == PromptType.SALES
    assert detect_prompt_type("хочу заказать экран") == PromptType.SALES


def test_defaults_to_default_type():
    assert detect_prompt_type("привет, как дела?") == PromptType.DEFAULT


def test_calculator_takes_priority_over_sales_when_both_match():
    # "мощность" (calculator) and "стоимость" (sales) both present
    assert detect_prompt_type("посчитай стоимость по мощности 5кВт") == PromptType.CALCULATOR


def test_get_system_prompt_returns_type_specific_text():
    assert "калькулятор" in get_system_prompt(PromptType.CALCULATOR).lower()
    assert "продаж" in get_system_prompt(PromptType.SALES).lower()
    assert get_system_prompt(PromptType.DEFAULT) == get_system_prompt()


def test_get_system_prompt_falls_back_to_default_for_unknown_type():
    assert get_system_prompt("nonsense") == get_system_prompt(PromptType.DEFAULT)


def test_get_system_prompt_appends_capabilities_when_configured(tmp_path):
    load_capabilities_summary.cache_clear()
    config = tmp_path / "capabilities.yaml"
    config.write_text(
        "capabilities:\n  - name: Тест\n    description: Проверка подключения.\n", encoding="utf-8"
    )

    with patch("app.core.prompt_manager.settings") as settings_mock:
        settings_mock.CAPABILITIES_PATH = str(config)
        prompt = get_system_prompt(PromptType.DEFAULT)

    assert "Тест: Проверка подключения." in prompt
    load_capabilities_summary.cache_clear()


def test_get_system_prompt_omits_capabilities_block_when_file_missing(tmp_path):
    load_capabilities_summary.cache_clear()

    with patch("app.core.prompt_manager.settings") as settings_mock:
        settings_mock.CAPABILITIES_PATH = str(tmp_path / "nope.yaml")
        prompt = get_system_prompt(PromptType.DEFAULT)

    assert "Возможности системы" not in prompt
    load_capabilities_summary.cache_clear()


def test_get_system_prompt_always_includes_golden_standard():
    # Unconditional for every prompt type, not just PromptType.CALCULATOR —
    # equipment/BOM answers can come up in sales or default chat too.
    for prompt_type in PromptType:
        prompt = get_system_prompt(prompt_type)
        assert "NovaStar" in prompt
        assert "Подрезка модулей ЗАПРЕЩЕНА" in prompt
        assert "1.3" in prompt


def test_get_system_prompt_instructs_russian_only():
    for prompt_type in PromptType:
        prompt = get_system_prompt(prompt_type).lower()
        assert "русском языке" in prompt


def test_get_system_prompt_instructs_capability_questions_use_capabilities_list():
    prompt = get_system_prompt(PromptType.DEFAULT)
    assert "умеешь ли ты" in prompt.lower()
    assert "возможности" in prompt.lower()


@pytest.mark.parametrize(
    "text",
    [
        "умеешь ли ты работать с чертежами",
        "можешь ли ты читать PDF",
        "что ты умеешь",
        "что ты можешь",
        "расскажи про твои возможности",
        "какой у тебя функционал",
        "с чем ты работаешь",
        "какие форматы ты поддерживаешь",
    ],
)
def test_is_capability_question_matches_common_phrasings(text):
    assert is_capability_question(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "какой стандартный размер модуля",
        "рассчитай мощность экрана",
        "сколько стоит комплект",
        "привет",
    ],
)
def test_is_capability_question_does_not_match_regular_questions(text):
    assert is_capability_question(text) is False
