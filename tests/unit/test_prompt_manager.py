from app.core.prompt_manager import PromptType, detect_prompt_type, get_system_prompt


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
