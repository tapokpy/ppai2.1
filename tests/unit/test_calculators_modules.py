import pytest

from app.services.calculators.modules import calculate_modules


def test_calculate_modules_basic_grid():
    result = calculate_modules(width_m=3.0, height_m=2.0, pixel_pitch_mm=2.5, module_size_m=0.5)

    assert result.columns == 6
    assert result.rows == 4
    assert result.total_modules == 24
    assert result.area_m2 == 6.0
    assert result.resolution_width_px == 6 * 200
    assert result.resolution_height_px == 4 * 200


def test_calculate_modules_rounds_up_partial_modules():
    result = calculate_modules(width_m=3.2, height_m=2.1, pixel_pitch_mm=2.5, module_size_m=0.5)

    assert result.columns == 7
    assert result.rows == 5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"width_m": 0, "height_m": 2.0, "pixel_pitch_mm": 2.5},
        {"width_m": 3.0, "height_m": -1.0, "pixel_pitch_mm": 2.5},
        {"width_m": 3.0, "height_m": 2.0, "pixel_pitch_mm": 0},
        {"width_m": 3.0, "height_m": 2.0, "pixel_pitch_mm": 2.5, "module_size_m": 0},
    ],
)
def test_calculate_modules_rejects_invalid_input(kwargs):
    with pytest.raises(ValueError):
        calculate_modules(**kwargs)
