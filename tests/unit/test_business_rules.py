import pytest

from app.models.sqlalchemy.business_rule import RuleSeverity
from app.services.business_rules import RuleParseError, parse_condition, parse_rule_definition


def test_parse_condition_supports_all_operators():
    assert parse_condition("pixel_pitch<2.5") == {"field": "pixel_pitch", "operator": "<", "value": 2.5}
    assert parse_condition("width_m>=10") == {"field": "width_m", "operator": ">=", "value": 10.0}
    assert parse_condition("module_count!=48") == {"field": "module_count", "operator": "!=", "value": 48.0}
    assert parse_condition("module_power_w==200") == {
        "field": "module_power_w",
        "operator": "==",
        "value": 200.0,
    }


def test_parse_condition_rejects_garbage():
    with pytest.raises(RuleParseError):
        parse_condition("not a condition")


def test_parse_rule_definition_plain_text_is_legacy_rule():
    conditions, message, severity = parse_rule_definition("Проверять комплектацию БП")

    assert conditions is None
    assert message == "Проверять комплектацию БП"
    assert severity == RuleSeverity.WARNING


def test_parse_rule_definition_structured_rule():
    conditions, message, severity = parse_rule_definition(
        "pixel_pitch<2.5,width_m>10 ; Риск перегрева ; BLOCKING"
    )

    assert conditions == [
        {"field": "pixel_pitch", "operator": "<", "value": 2.5},
        {"field": "width_m", "operator": ">", "value": 10.0},
    ]
    assert message == "Риск перегрева"
    assert severity == RuleSeverity.BLOCKING


def test_parse_rule_definition_defaults_severity_to_warning():
    conditions, message, severity = parse_rule_definition("pixel_pitch<2.5 ; Внимание")

    assert severity == RuleSeverity.WARNING
    assert message == "Внимание"


def test_parse_rule_definition_rejects_unknown_severity():
    with pytest.raises(RuleParseError):
        parse_rule_definition("pixel_pitch<2.5 ; Внимание ; CRITICAL")


def test_parse_rule_definition_rejects_missing_message():
    with pytest.raises(RuleParseError):
        parse_rule_definition("pixel_pitch<2.5 ; ")
