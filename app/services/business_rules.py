import operator
import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlalchemy.business_rule import BusinessRule, RuleSeverity

# Longest operators first so "<=" isn't matched as "<" followed by "=".
_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
}
_OPERATOR_PATTERN = "|".join(re.escape(op) for op in sorted(_OPERATORS, key=len, reverse=True))
_CONDITION_RE = re.compile(rf"^(?P<field>[a-zA-Z_][a-zA-Z0-9_]*)(?P<op>{_OPERATOR_PATTERN})(?P<value>-?\d+(\.\d+)?)$")


class RuleParseError(ValueError):
    pass


@dataclass
class RuleViolation:
    rule_text: str
    severity: RuleSeverity


def parse_condition(raw: str) -> dict[str, Any]:
    match = _CONDITION_RE.match(raw.strip())
    if not match:
        raise RuleParseError(f"Некорректное условие: '{raw}'")

    return {
        "field": match.group("field"),
        "operator": match.group("op"),
        "value": float(match.group("value")),
    }


def parse_rule_definition(raw_text: str) -> tuple[list[dict[str, Any]] | None, str, RuleSeverity]:
    """Parse admin-supplied rule text.

    Two forms are supported:
      - Plain text (no ';'): stored as a legacy free-text rule, matched by
        substring against the calculation context.
      - "<cond>[,<cond>...] ; <message> [; SEVERITY]": structured AND-conditions
        evaluated against numeric calculation context fields.
    """
    if ";" not in raw_text:
        return None, raw_text.strip(), RuleSeverity.WARNING

    parts = [part.strip() for part in raw_text.split(";")]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise RuleParseError("Ожидается формат: <условия> ; <сообщение> [; SEVERITY]")

    conditions_part, message = parts[0], parts[1]
    severity = RuleSeverity.WARNING
    if len(parts) >= 3 and parts[2]:
        try:
            severity = RuleSeverity(parts[2].upper())
        except ValueError as exc:
            raise RuleParseError(
                f"Неизвестная серьёзность '{parts[2]}', ожидается INFO, WARNING или BLOCKING"
            ) from exc

    conditions = [parse_condition(raw) for raw in conditions_part.split(",")]
    return conditions, message, severity


def _condition_matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if condition["field"] not in context:
        return False

    try:
        actual_value = float(context[condition["field"]])
    except (TypeError, ValueError):
        return False

    return _OPERATORS[condition["operator"]](actual_value, condition["value"])


class BusinessRulesEngine:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def load_rules(self) -> list[BusinessRule]:
        result = await self._session.execute(select(BusinessRule))
        return list(result.scalars().all())

    async def add_rule(
        self,
        rule_text: str,
        severity: RuleSeverity = RuleSeverity.WARNING,
        conditions: list[dict[str, Any]] | None = None,
    ) -> BusinessRule:
        rule = BusinessRule(rule_text=rule_text, severity=severity, conditions=conditions)
        self._session.add(rule)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def add_rule_from_text(self, raw_text: str) -> BusinessRule:
        conditions, message, severity = parse_rule_definition(raw_text)
        return await self.add_rule(message, severity=severity, conditions=conditions)

    async def validate(self, calculation_context: dict[str, Any]) -> list[RuleViolation]:
        violations = []

        for rule in await self.load_rules():
            if rule.conditions:
                matched = all(_condition_matches(c, calculation_context) for c in rule.conditions)
            else:
                context_tokens = {str(value).lower() for value in calculation_context.values()}
                rule_text_lower = rule.rule_text.lower()
                matched = any(token in rule_text_lower for token in context_tokens)

            if matched:
                violations.append(RuleViolation(rule_text=rule.rule_text, severity=rule.severity))

        return violations
