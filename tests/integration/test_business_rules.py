import pytest

from app.core.database import async_session_maker
from app.models.sqlalchemy.business_rule import RuleSeverity
from app.services.business_rules import BusinessRulesEngine
from tests.integration.conftest import requires_postgres

pytestmark = requires_postgres


@pytest.mark.asyncio
async def test_add_and_load_rules(clean_db):
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule(
            "Шаг пикселя P10 требует минимум 1 кв.м", severity=RuleSeverity.BLOCKING
        )

    async with async_session_maker() as session:
        rules = await BusinessRulesEngine(session).load_rules()

    assert len(rules) == 1
    assert rules[0].severity == RuleSeverity.BLOCKING


@pytest.mark.asyncio
async def test_validate_matches_context_keywords(clean_db):
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule("Шаг пикселя p10 требует особого согласования")

    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate({"pixel_pitch": "p10"})

    assert len(violations) == 1
    assert "p10" in violations[0].rule_text.lower()


@pytest.mark.asyncio
async def test_validate_ignores_unrelated_rules(clean_db):
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule("Проверять комплектацию БП перед отгрузкой")

    async with async_session_maker() as session:
        violations = await BusinessRulesEngine(session).validate({"pixel_pitch": "p2.5"})

    assert violations == []


@pytest.mark.asyncio
async def test_validate_matches_structured_conditions(clean_db):
    async with async_session_maker() as session:
        await BusinessRulesEngine(session).add_rule(
            "Риск перегрева",
            severity=RuleSeverity.BLOCKING,
            conditions=[
                {"field": "pixel_pitch", "operator": "<", "value": 2.5},
                {"field": "width_m", "operator": ">", "value": 10},
            ],
        )

    async with async_session_maker() as session:
        matching = await BusinessRulesEngine(session).validate({"pixel_pitch": 2.0, "width_m": 12})
        non_matching = await BusinessRulesEngine(session).validate({"pixel_pitch": 3.0, "width_m": 12})
        missing_field = await BusinessRulesEngine(session).validate({"pixel_pitch": 2.0})

    assert len(matching) == 1
    assert matching[0].severity == RuleSeverity.BLOCKING
    assert non_matching == []
    assert missing_field == []


@pytest.mark.asyncio
async def test_add_rule_from_text_parses_structured_rule(clean_db):
    async with async_session_maker() as session:
        rule = await BusinessRulesEngine(session).add_rule_from_text(
            "module_count>50,module_power_w>=200 ; Требуется усиленное питание ; BLOCKING"
        )

    assert rule.rule_text == "Требуется усиленное питание"
    assert rule.severity == RuleSeverity.BLOCKING
    assert rule.conditions == [
        {"field": "module_count", "operator": ">", "value": 50.0},
        {"field": "module_power_w", "operator": ">=", "value": 200.0},
    ]


@pytest.mark.asyncio
async def test_add_rule_from_text_parses_legacy_plain_text(clean_db):
    async with async_session_maker() as session:
        rule = await BusinessRulesEngine(session).add_rule_from_text("Проверять комплектацию БП")

    assert rule.rule_text == "Проверять комплектацию БП"
    assert rule.conditions is None
    assert rule.severity == RuleSeverity.WARNING
