from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy.business_rule import BusinessRule, RuleSeverity


@dataclass
class RuleViolation:
    rule_text: str
    severity: RuleSeverity


class BusinessRulesEngine:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def load_rules(self) -> list[BusinessRule]:
        result = await self._session.execute(select(BusinessRule))
        return list(result.scalars().all())

    async def add_rule(self, rule_text: str, severity: RuleSeverity = RuleSeverity.WARNING) -> BusinessRule:
        rule = BusinessRule(rule_text=rule_text, severity=severity)
        self._session.add(rule)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def validate(self, calculation_context: dict[str, Any]) -> list[RuleViolation]:
        context_tokens = {str(value).lower() for value in calculation_context.values()}
        violations = []

        for rule in await self.load_rules():
            rule_text_lower = rule.rule_text.lower()
            if any(token in rule_text_lower for token in context_tokens):
                violations.append(RuleViolation(rule_text=rule.rule_text, severity=rule.severity))

        return violations
