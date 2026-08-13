import pytest

from app.services.calculators.led_bom import LedBomError, calculate_bom


def test_outdoor_basic_grid_and_resolution():
    # 7 cabinets across (960mm each = 6720mm), 1 row.
    result = calculate_bom(
        width_mm=6720, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=10
    )
    assert result.columns == 7
    assert result.rows == 1
    assert result.unit_count == 7
    # pixels_per_unit_side = round(960 / 2.5) = 384
    assert result.resolution_width_px == 7 * 384
    assert result.resolution_height_px == 384


def test_psu_count_jumps_exactly_at_outdoor_module_cap():
    # module_power_w kept tiny so the power-based PSU count stays at 1 in
    # both cases — isolates the "max 7 modules per PSU" cap as the only
    # thing that can move psu_count.
    at_cap = calculate_bom(
        width_mm=960 * 7, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=10
    )
    over_cap = calculate_bom(
        width_mm=960 * 8, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=10
    )

    assert at_cap.unit_count == 7
    assert at_cap.psu_count == 1
    assert over_cap.unit_count == 8
    assert over_cap.psu_count == 2


def test_indoor_psu_cap_is_ten_modules():
    at_cap = calculate_bom(
        width_mm=640 * 10, height_mm=640, pixel_pitch_mm=1.9, screen_type="indoor", module_power_w=5
    )
    over_cap = calculate_bom(
        width_mm=640 * 11, height_mm=640, pixel_pitch_mm=1.9, screen_type="indoor", module_power_w=5
    )

    assert at_cap.psu_count == 1
    assert over_cap.psu_count == 2


def test_voltage_switches_to_380_at_15kw_threshold():
    # Synthetic boundary values chosen so peak_with_margin lands just below
    # / just at-and-above 15000 W exactly (1 cabinet, margin = power * 1.3).
    just_under = calculate_bom(
        width_mm=960, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=11538
    )
    at_threshold = calculate_bom(
        width_mm=960, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=11539
    )

    assert just_under.peak_power_with_margin_kw < 15.0
    assert just_under.voltage_v == 220
    assert at_threshold.peak_power_with_margin_kw >= 15.0
    assert at_threshold.voltage_v == 380


def test_power_margin_is_1_3_not_legacy_1_2():
    result = calculate_bom(
        width_mm=960, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=100
    )
    assert result.peak_power_kw == 0.1
    assert result.peak_power_with_margin_kw == pytest.approx(0.13)


def test_zip_percentages_rounded_up():
    # 3 cabinets wide x 7 tall = 21 units -> zip_modules = ceil(21*0.05) = 2.
    # psu_count = max(power-based=1, unit-cap ceil(21/7)=3) = 3 -> zip_psu = ceil(3*0.03) = 1.
    # card_count = 21 -> zip_cards = ceil(21*0.03) = 1.
    result = calculate_bom(
        width_mm=960 * 3, height_mm=960 * 7, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=10
    )
    assert result.unit_count == 21
    assert result.psu_count == 3
    assert result.zip_modules == 2
    assert result.zip_psu == 1
    assert result.zip_cards == 1


def test_port_count_from_pixel_capacity():
    # A screen big enough to need more than one 650,000px port.
    result = calculate_bom(
        width_mm=960 * 10, height_mm=960 * 10, pixel_pitch_mm=1.0, screen_type="outdoor", module_power_w=10
    )
    assert result.total_pixels > 650_000
    assert result.port_count == pytest.approx(-(-result.total_pixels // 650_000))


def test_open_frame_requires_pitch_above_p2():
    with pytest.raises(LedBomError, match="P2"):
        calculate_bom(
            width_mm=1000,
            height_mm=1000,
            pixel_pitch_mm=2.0,
            screen_type="open_frame",
            module_power_w=50,
            module_size_mm=250,
        )


def test_open_frame_requires_module_size():
    with pytest.raises(LedBomError, match="размер модуля"):
        calculate_bom(
            width_mm=1000, height_mm=1000, pixel_pitch_mm=2.5, screen_type="open_frame", module_power_w=50
        )


def test_open_frame_succeeds_with_explicit_module_size_and_psu():
    result = calculate_bom(
        width_mm=1000,
        height_mm=1000,
        pixel_pitch_mm=2.5,
        screen_type="open_frame",
        module_power_w=50,
        module_size_mm=250,
        psu_power_w=300,
    )
    assert result.columns == 4
    assert result.rows == 4
    assert result.unit_count == 16


def test_rental_without_psu_power_raises():
    with pytest.raises(LedBomError, match="psu_power_w"):
        calculate_bom(
            width_mm=1000, height_mm=1000, pixel_pitch_mm=3.9, screen_type="rental", module_power_w=50
        )


def test_rental_with_explicit_psu_power_succeeds():
    result = calculate_bom(
        width_mm=1000, height_mm=1000, pixel_pitch_mm=3.9, screen_type="rental", module_power_w=50, psu_power_w=350
    )
    assert result.psu_power_w == 350


def test_unknown_screen_type_raises():
    with pytest.raises(LedBomError, match="Неизвестный тип"):
        calculate_bom(width_mm=1000, height_mm=1000, pixel_pitch_mm=2.5, screen_type="bogus", module_power_w=50)


def test_to_rows_includes_all_bom_lines():
    result = calculate_bom(
        width_mm=960, height_mm=960, pixel_pitch_mm=2.5, screen_type="outdoor", module_power_w=10
    )
    names = {row["name"] for row in result.to_rows()}
    assert "Кабинет/модуль" in names
    assert "Блок питания" in names
    assert "Приёмная карта" in names
    assert "Порты контроллера" in names
    assert any("ЗИП" in name for name in names)
