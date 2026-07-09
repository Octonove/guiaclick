"""Tests de logica pura de GuiaClick (sin captura real de pantalla)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from guiaclick import capture, guide  # noqa: E402


def make_step(w=240, h=140, x=60, y=70, window="Documento - Bloc de notas", button="left"):
    return capture.Step(image=Image.new("RGB", (w, h), (200, 210, 230)),
                        x=x, y=y, window=window, button=button)


def test_clean_window_title():
    assert guide.clean_window_title("Factura.pdf - Adobe Acrobat") == "Factura.pdf"
    assert guide.clean_window_title("Inicio — Mozilla Firefox") == "Inicio"
    assert guide.clean_window_title("  Solo  ") == "Solo"
    assert guide.clean_window_title("") == ""


def test_auto_title():
    # clean_window_title se queda con el nombre del documento, no con la app
    assert "Documento" in guide.auto_title(make_step(), 1)
    assert guide.auto_title(make_step(window=""), 3) == "Haz clic (paso 3)"
    assert guide.auto_title(make_step(button="right"), 1).startswith("Haz clic derecho")


def test_hex_to_rgb():
    assert guide._hex_to_rgb("#CE6E61") == (206, 110, 97)
    assert guide._hex_to_rgb("#fff") == (255, 255, 255)
    assert guide._hex_to_rgb("basura") == (206, 110, 97)


def test_render_step_returns_image():
    img = guide.render_step(make_step(), 1)
    assert img.width > 0 and img.height > 0


def test_render_step_scales_down():
    big = make_step(w=3000, h=1800, x=1500, y=900)
    img = guide.render_step(big, 1, max_width=1000)
    assert img.width == 1000


def test_render_step_with_blur():
    st = make_step()
    st.blur = [(10, 10, 80, 50)]
    img = guide.render_step(st, 1)   # no debe lanzar
    assert img.width > 0


def test_render_blur_out_of_bounds_ignored():
    st = make_step()
    st.blur = [(-50, -50, 99999, 99999), (5, 5, 5, 5)]  # fuera de rango / vacio
    img = guide.render_step(st, 1)
    assert img.width > 0


def test_export_html(tmp_path):
    out = str(tmp_path / "g.html")
    guide.export_html([make_step(), make_step(window="Excel")], out, title="Mi Guia")
    content = Path(out).read_text(encoding="utf-8")
    assert "<h1>Mi Guia</h1>" in content
    assert "data:image/png;base64," in content
    assert content.count('class="step"') == 2


def test_export_html_escapes(tmp_path):
    st = make_step(window="<script>")
    st.title = "<b>Titulo</b> & cosas"
    st.note = "<img onerror=alert(1)>"
    out = str(tmp_path / "x.html")
    guide.export_html([st], out, title="A & B <x>")
    c = Path(out).read_text(encoding="utf-8")
    assert "<script>" not in c.replace("data:image/png;base64", "")
    assert "&amp;" in c and "&lt;" in c


def test_export_markdown(tmp_path):
    out = str(tmp_path / "g.md")
    guide.export_markdown([make_step(), make_step()], out, title="Guia MD")
    assert Path(out).is_file()
    imgs = list((tmp_path / "g_imagenes").glob("*.png"))
    assert len(imgs) == 2


def test_export_pdf(tmp_path):
    import fitz
    out = str(tmp_path / "g.pdf")
    guide.export_pdf([make_step(), make_step(), make_step()], out, title="Guia PDF")
    doc = fitz.open(out)
    assert doc.page_count == 4  # portada + 3 pasos
    doc.close()


def test_md_escape():
    assert guide._md_escape("# Titulo *raro* [x]") == r"\# Titulo \*raro\* \[x\]"
    assert "\n" not in guide._md_escape("linea1\nlinea2")


def test_export_markdown_escapes(tmp_path):
    st = make_step()
    st.title = "## Inyeccion [link](http://x)"
    out = str(tmp_path / "e.md")
    guide.export_markdown([st], out, title="T")
    c = Path(out).read_text(encoding="utf-8")
    assert r"\#\# Inyeccion" in c


def test_title_or_auto():
    st = make_step()
    assert guide.title_or_auto(st, 1).startswith("Haz clic")
    st.title = "Mi paso"
    assert guide.title_or_auto(st, 1) == "Mi paso"
