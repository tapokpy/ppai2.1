import pytest

from app.services.tools import calculate_power_tool


@pytest.mark.asyncio
async def test_run_returns_calculated_result():
    result = await calculate_power_tool.run(module_count=20, module_power_w=45)

    assert result.success is True
    assert "кВт" in result.text
    assert result.structured_data["kind"] == "power_calculation"
    assert result.structured_data["items"][0]["name"] == "Блок питания"


@pytest.mark.asyncio
async def test_run_coerces_string_arguments_from_the_model():
    # Native tool-calling can hand back numbers as strings depending on the
    # model — the real calculator function requires int/float.
    result = await calculate_power_tool.run(module_count="20", module_power_w="45")

    assert result.success is True


@pytest.mark.asyncio
async def test_run_reports_friendly_error_instead_of_raising():
    result = await calculate_power_tool.run(module_count=0, module_power_w=45)

    assert result.success is False
    assert result.error
    assert result.structured_data is None


def test_tool_spec_declares_required_parameters():
    names = {p.name for p in calculate_power_tool.TOOL_SPEC.parameters}
    assert names == {"module_count", "module_power_w"}
    assert all(p.required for p in calculate_power_tool.TOOL_SPEC.parameters)
