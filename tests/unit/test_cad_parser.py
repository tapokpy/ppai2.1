from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.cad_parser import (
    CadConversionError,
    CadParseError,
    UnsupportedCadFormatError,
    VisionNotConfiguredError,
    analyze_drawing_vision,
    convert_dwg_to_dxf,
    extract_data,
    generate_drawing,
    generate_frame,
    generate_plate,
    open_drawing,
    render_to_pdf,
    render_to_png,
)


def test_generate_frame_and_extract_data_round_trip(tmp_path):
    doc = generate_frame(width=1000, height=500)
    extracted = extract_data(doc)

    assert extracted.entity_counts.get("LWPOLYLINE") == 1
    assert extracted.entity_counts.get("TEXT") == 1
    assert extracted.texts == ["1000 x 500"]


def test_generate_plate_has_four_holes():
    doc = generate_plate(width=200, height=100, hole_diameter=6, hole_margin=15)
    extracted = extract_data(doc)

    assert extracted.entity_counts.get("CIRCLE") == 4
    assert extracted.entity_counts.get("LWPOLYLINE") == 1


def test_generate_drawing_saves_dxf_file(tmp_path):
    output_path = generate_drawing("frame", 1000, 500, tmp_path, "Тестовый проект")

    assert output_path.exists()
    assert output_path.suffix == ".dxf"

    # Round-trips through open_drawing like a real upload would.
    doc, doc_type = open_drawing(output_path)
    assert doc_type == "dxf"
    extracted = extract_data(doc)
    assert extracted.texts == ["1000 x 500"]


def test_generate_drawing_rejects_unknown_shape(tmp_path):
    with pytest.raises(UnsupportedCadFormatError):
        generate_drawing("triangle", 100, 100, tmp_path, "x")


def test_generate_drawing_sanitizes_project_name_for_filesystem(tmp_path):
    output_path = generate_drawing("frame", 100, 100, tmp_path, "проект: тест/весёлый")

    assert output_path.exists()
    assert "/" not in output_path.name
    assert ":" not in output_path.name


def test_open_drawing_rejects_cdr():
    with pytest.raises(UnsupportedCadFormatError):
        open_drawing(Path("drawing.cdr"))


def test_open_drawing_rejects_unknown_extension():
    with pytest.raises(UnsupportedCadFormatError):
        open_drawing(Path("drawing.xyz"))


def test_open_drawing_raises_parse_error_for_invalid_dxf(tmp_path):
    bad_file = tmp_path / "broken.dxf"
    bad_file.write_text("this is not a real dxf file", encoding="utf-8")

    with pytest.raises(CadParseError):
        open_drawing(bad_file)


def test_convert_dwg_to_dxf_requires_configured_converter(tmp_path):
    fake_dwg = tmp_path / "drawing.dwg"
    fake_dwg.write_bytes(b"fake")

    with pytest.raises(CadConversionError):
        convert_dwg_to_dxf(fake_dwg, tmp_path, converter_path="")


def test_convert_dwg_to_dxf_wraps_subprocess_failure(tmp_path):
    fake_dwg = tmp_path / "drawing.dwg"
    fake_dwg.write_bytes(b"fake")

    with patch("app.services.cad_parser.subprocess.run", side_effect=FileNotFoundError("no such file")):
        with pytest.raises(CadConversionError):
            convert_dwg_to_dxf(fake_dwg, tmp_path, converter_path="/usr/bin/does-not-exist")


def test_open_drawing_dispatches_dwg_through_converter(tmp_path):
    fake_dwg = tmp_path / "drawing.dwg"
    fake_dwg.write_bytes(b"fake")
    converted_doc = generate_frame(50, 50)

    def _fake_convert(dwg_path, output_dir, converter_path):
        dxf_path = output_dir / "drawing.dxf"
        converted_doc.saveas(str(dxf_path))
        return dxf_path

    with patch("app.services.cad_parser.convert_dwg_to_dxf", side_effect=_fake_convert):
        doc, doc_type = open_drawing(fake_dwg, converter_path="/fake/converter")

    assert doc_type == "dwg"
    assert extract_data(doc).texts == ["50 x 50"]


def test_render_to_pdf_produces_real_file(tmp_path):
    doc = generate_frame(100, 100)
    output_path = tmp_path / "render.pdf"

    result = render_to_pdf(doc, output_path)

    assert result == output_path
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_render_to_png_produces_real_file(tmp_path):
    doc = generate_plate(100, 100)
    output_path = tmp_path / "render.png"

    render_to_png(doc, output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_analyze_drawing_vision_raises_not_configured():
    with pytest.raises(VisionNotConfiguredError):
        analyze_drawing_vision(Path("whatever.png"))
