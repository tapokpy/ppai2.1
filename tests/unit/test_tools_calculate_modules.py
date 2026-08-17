import pytest

from app.services.tools import calculate_modules_tool


@pytest.mark.asyncio
async def test_run_returns_calculated_result():
    result = await calculate_modules_tool.run(width_m=3.0, height_m=2.0, pixel_pitch_mm=2.5)

    assert result.success is True
    assert "Модулей" in result.text
    assert "Разрешение" in result.text


@pytest.mark.asyncio
async def test_run_coerces_string_arguments():
    result = await calculate_modules_tool.run(width_m="3.0", height_m="2.0", pixel_pitch_mm="2.5")

    assert result.success is True


@pytest.mark.asyncio
async def test_run_reports_friendly_error_instead_of_raising():
    result = await calculate_modules_tool.run(width_m=0, height_m=2.0, pixel_pitch_mm=2.5)

    assert result.success is False
    assert result.error


def test_tool_spec_declares_required_parameters():
    names = {p.name for p in calculate_modules_tool.TOOL_SPEC.parameters}
    assert names == {"width_m", "height_m", "pixel_pitch_mm"}
    assert all(p.required for p in calculate_modules_tool.TOOL_SPEC.parameters)
