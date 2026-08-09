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
