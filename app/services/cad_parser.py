import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from loguru import logger

SUPPORTED_READ_EXTENSIONS = {".dxf", ".dwg"}
NATIVE_EXTENSIONS = {".dxf"}


class UnsupportedCadFormatError(Exception):
    """Raised for formats with no feasible read path at all (.cdr and
    anything else) — ezdxf only understands DXF, and there's no free
    converter for CorelDRAW the way ODA File Converter exists for DWG."""


class CadConversionError(Exception):
    """Raised when a .dwg needs the (optional, not-Python) ODA File
    Converter and it isn't configured/installed, or the conversion itself
    fails. Distinct from UnsupportedCadFormatError: DWG *is* supportable,
    just not by ezdxf alone."""


class CadParseError(Exception):
    """Raised when ezdxf can open the file but the DXF content itself is
    invalid/corrupt."""


class VisionNotConfiguredError(Exception):
    """Raised by analyze_drawing_vision() — the local model (qwen2.5:7b)
    has no vision capability, and cloud (which would) is currently
    disabled (settings.CLOUD_ENABLED=False). A deliberate stub, not a bug:
    callers should show this as a clear "not available yet" message."""


@dataclass
class ExtractedCadData:
    entity_counts: dict[str, int] = field(default_factory=dict)
    texts: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"entity_counts": self.entity_counts, "texts": self.texts, "dimensions": self.dimensions}


def convert_dwg_to_dxf(dwg_path: Path, output_dir: Path, converter_path: str) -> Path:
    """Shells out to ODA File Converter (https://www.opendesign.com/guestfiles/oda_file_converter)
    — the standard free tool for DWG->DXF conversion; ezdxf itself only
    reads DXF. Its CLI batch mode operates on whole folders, not single
    files, so this isolates the input in its own temp folder first."""
    if not converter_path:
        raise CadConversionError(
            "Для чтения .dwg нужен ODA File Converter — он не настроен "
            "(ODA_FILE_CONVERTER_PATH пуст). Установите конвертер или пришлите файл в .dxf."
        )

    with tempfile.TemporaryDirectory() as tmp_in:
        tmp_in_path = Path(tmp_in)
        staged = tmp_in_path / dwg_path.name
        staged.write_bytes(dwg_path.read_bytes())

        try:
            subprocess.run(
                [converter_path, str(tmp_in_path), str(output_dir), "ACAD2018", "DXF", "0", "1"],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise CadConversionError(f"Конвертация .dwg в .dxf не удалась: {exc}") from exc

        converted = output_dir / f"{staged.stem}.dxf"
        if not converted.exists():
            raise CadConversionError("ODA File Converter отработал, но .dxf файл не появился.")
        return converted


def open_drawing(file_path: Path, converter_path: str = "") -> tuple[Drawing, str]:
    """Returns (ezdxf Drawing, doc_type). Dispatches by extension —
    .cdr and anything else fail fast with UnsupportedCadFormatError since
    there's no feasible read path, not just a missing optional tool.

    Callers that want to keep the drawing (not just inspect it in memory)
    should doc.saveas(...) themselves afterward — this function's own DWG
    conversion output lives in a throwaway temp dir, not any persistent
    storage, so there's exactly one place a canonical copy gets written."""
    ext = file_path.suffix.lower()

    if ext == ".dxf":
        doc = _read_dxf(file_path)
        return doc, "dxf"

    if ext == ".dwg":
        with tempfile.TemporaryDirectory() as tmp_out:
            dxf_path = convert_dwg_to_dxf(file_path, Path(tmp_out), converter_path)
            doc = _read_dxf(dxf_path)
        return doc, "dwg"

    if ext == ".cdr":
        raise UnsupportedCadFormatError(
            "Формат .cdr (CorelDRAW) не поддерживается — это не DXF/DWG-совместимый "
            "формат, и открытого инструмента для его чтения нет. Пришлите чертёж в .dxf или .dwg."
        )

    raise UnsupportedCadFormatError(f"Формат {ext or '(без расширения)'} не поддерживается.")


def _read_dxf(dxf_path: Path) -> Drawing:
    try:
        return ezdxf.readfile(str(dxf_path))
    except (ezdxf.DXFError, OSError) as exc:
        # ezdxf.readfile() raises plain OSError (not DXFError) when the
        # content doesn't even look like DXF, vs. DXFError for a file that
        # passes the format sniff but is structurally broken — both are
        # "can't parse this as DXF" from the caller's point of view.
        raise CadParseError(f"Не удалось разобрать DXF: {exc}") from exc


def extract_data(doc: Drawing) -> ExtractedCadData:
    """Pulls whatever cad_parser can reliably get from any DXF: entity
    counts, text annotations (TEXT/MTEXT), and dimension measurement
    strings. Deliberately not a full BOM extractor — that's fuzzy,
    drawing-convention-dependent work with no spec'd format to target."""
    msp = doc.modelspace()
    data = ExtractedCadData()

    for entity in msp:
        dxftype = entity.dxftype()
        data.entity_counts[dxftype] = data.entity_counts.get(dxftype, 0) + 1

        if dxftype == "TEXT":
            data.texts.append(entity.dxf.text)
        elif dxftype == "MTEXT":
            data.texts.append(entity.plain_text())
        elif dxftype == "DIMENSION":
            try:
                data.dimensions.append(entity.get_measurement_text())
            except Exception as exc:
                # Missing/invalid dimension style or measurement override —
                # not fatal to the rest of extraction, but silent about it
                # meant "dimensions: []" looked identical to "drawing truly
                # has none" from the user's side. Logged so an admin can at
                # least tell the two apart when a user reports "no размеры".
                logger.warning(f"Failed to read DIMENSION measurement text: {exc}")

    return data


def render_to_pdf(doc: Drawing, output_path: Path) -> Path:
    return _render(doc, output_path)


def render_to_png(doc: Drawing, output_path: Path) -> Path:
    return _render(doc, output_path)


def _render(doc: Drawing, output_path: Path) -> Path:
    # Imported lazily — matplotlib is a heavyish dependency only needed
    # for this one rendering step.
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    context = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    Frontend(context, backend).draw_layout(doc.modelspace(), finalize=True)
    fig.savefig(str(output_path), dpi=200)
    plt.close(fig)
    return output_path


def generate_frame(width: float, height: float) -> Drawing:
    """A simple rectangular outline (крепёжная рамка) with a dimension
    label — the spec's own worked example ("Создай чертеж рамки 1000х500")."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    points = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    msp.add_lwpolyline(points, close=True)
    msp.add_text(f"{width:g} x {height:g}", height=min(width, height) * 0.05).set_placement(
        (width / 2, -min(width, height) * 0.08)
    )
    return doc


def generate_plate(width: float, height: float, hole_diameter: float = 8.0, hole_margin: float = 20.0) -> Drawing:
    """A solid rectangular mounting plate with a corner mounting hole
    near each corner — the spec's other named example ("крепёжные пластины")."""
    doc = ezdxf.new(setup=True)
    msp = doc.modelspace()
    points = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
    msp.add_lwpolyline(points, close=True)

    radius = hole_diameter / 2
    for x in (hole_margin, width - hole_margin):
        for y in (hole_margin, height - hole_margin):
            msp.add_circle((x, y), radius)

    msp.add_text(f"{width:g} x {height:g}", height=min(width, height) * 0.05).set_placement(
        (width / 2, -min(width, height) * 0.08)
    )
    return doc


_GENERATORS = {"frame": generate_frame, "plate": generate_plate}
SUPPORTED_SHAPES = tuple(_GENERATORS)


def generate_drawing(shape: str, width: float, height: float, storage_dir: Path, project_name: str) -> Path:
    generator = _GENERATORS.get(shape)
    if generator is None:
        raise UnsupportedCadFormatError(
            f"Не умею генерировать «{shape}» — доступны: {', '.join(_GENERATORS)}."
        )

    doc = generator(width, height)
    storage_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)[:80] or "drawing"
    output_path = storage_dir / f"{safe_name}.dxf"
    doc.saveas(str(output_path))
    logger.info(f"Generated {shape} drawing {width}x{height} -> {output_path}")
    return output_path


def analyze_drawing_vision(image_path: Path) -> str:
    raise VisionNotConfiguredError(
        "Vision-анализ чертежей пока недоступен — локальная модель (qwen2.5:7b) без "
        "зрения, облачный ИИ временно отключён. Извлечение текста/размеров/геометрии "
        "через ezdxf работает уже сейчас — визуальный анализ добавим отдельно, когда "
        "подключим vision-модель."
    )
