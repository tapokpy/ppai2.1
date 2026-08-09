import pytest

from app.services.calculators.power_cables import calculate_power_and_cables


def test_calculate_power_and_cables_basic():
    result = calculate_power_and_cables(
        module_count=10, module_power_w=100, psu_power_w=200, voltage_v=220
    )

    assert result.total_power_kw == 1.2
    assert result.breaker_rating_a == 10
    assert result.cable_cross_section_mm2 == 1.5
    assert result.psu_count == 6
    assert result.power_reserve == 0.2


def test_calculate_power_and_cables_scales_with_larger_screen():
    result = calculate_power_and_cables(
        module_count=100, module_power_w=100, psu_power_w=480, voltage_v=220
    )

    assert result.total_power_kw == 12.0
    assert result.breaker_rating_a == 80
    assert result.cable_cross_section_mm2 == 16.0
    assert result.psu_count == 25


@pytest.mark.parametrize(
    "kwargs",
    [
        {"module_count": 0, "module_power_w": 100},
        {"module_count": 10, "module_power_w": 0},
        {"module_count": 10, "module_power_w": 100, "psu_power_w": 0},
    ],
)
def test_calculate_power_and_cables_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):
        calculate_power_and_cables(**kwargs)
