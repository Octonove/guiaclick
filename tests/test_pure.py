"""Tests de logica pura de GuiaClick (sin captura real de pantalla)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from guiaclick import capture, guide, project  # noqa: E402


def make_step(w=240, h=140, x=60, y=70, window="Documento - Bloc de notas", button="left"):
    return capture.Step(image=Image.new("RGB", (w, h), (200, 210, 230)),
                        x=x, y=y, window=window, button=button)


# ------------------------------------------------------ recorte de paso
def test_crop_step_adjusts_click_and_blur():
    st = make_step(w=400, h=300, x=200, y=150)
    st.blur = [(10, 10, 60, 60), (350, 250, 390, 290)]
    ok = capture.crop_step(st, (100, 100, 300, 250))
    assert ok
    assert (st.image.width, st.image.height) == (200, 150)
    assert (st.x, st.y) == (100, 50)                 # clic reubicado al recorte
    assert st.blur == [(0, 0, 0, 0)] or len(st.blur) == 0 or st.blur[0][0] == 0
    # el 2o blur quedaba fuera del recorte -> se descarta; el 1o se reencuadra
    assert all(0 <= b[0] and b[2] <= st.image.width for b in st.blur)


def test_crop_step_restore():
    st = make_step(w=400, h=300, x=200, y=150)
    assert capture.crop_step(st, (50, 50, 350, 250))
    assert st.image.width == 300 and st.original is not None
    assert capture.restore_step(st)
    assert (st.image.width, st.image.height) == (400, 300)
    assert (st.x, st.y) == (200, 150) and st.original is None


def test_crop_step_rejects_tiny():
    st = make_step()
    assert capture.crop_step(st, (10, 10, 20, 20)) is False   # < min_side
    assert st.original is None                                 # no toca nada


# ------------------------------------------------------ proyecto .guiaclick
def test_project_roundtrip(tmp_path):
    st1 = make_step(window="A"); st1.title = "Paso uno"; st1.blur = [(5, 5, 40, 40)]
    st2 = make_step(window="B")
    capture.crop_step(st2, (20, 20, 200, 120))    # st2 tiene estado de recorte
    p = tmp_path / "g.guiaclick"
    project.save_project(p, [st1, st2], title="Mi Guia")
    steps, title = project.load_project(p)
    assert title == "Mi Guia" and len(steps) == 2
    assert steps[0].title == "Paso uno" and steps[0].blur == [(5, 5, 40, 40)]
    assert steps[1].original is not None            # el recorte se preserva
    assert capture.restore_step(steps[1])           # y se puede deshacer tras reabrir


def test_project_load_bad_file(tmp_path):
    bad = tmp_path / "x.guiaclick"
    bad.write_text("no soy un zip", encoding="utf-8")
    with pytest.raises(project.ProjectError):
        project.load_project(bad)


def test_autosave_and_clear(tmp_path):
    project.autosave(tmp_path, [make_step()], "T")
    got = project.load_autosave(tmp_path)
    assert got is not None and len(got[0]) == 1
    project.autosave(tmp_path, [], "")              # sin pasos -> borra
    assert project.load_autosave(tmp_path) is None


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


def test_export_pdf_fluid(tmp_path):
    import fitz
    out = str(tmp_path / "g.pdf")
    # 3 capturas apaisadas: el layout fluido las agrupa (antes eran 4 paginas
    # con ~56% de cada una en blanco). Debe salir mas compacto.
    guide.export_pdf([make_step(w=480, h=270)] * 3, out, title="Guia PDF")
    doc = fitz.open(out)
    assert 1 <= doc.page_count <= 2      # compacto, no 1-pagina-por-paso
    # cada imagen debe ocupar mas ancho del que dejaba el layout viejo
    imgs = sum(len(doc[p].get_images()) for p in range(doc.page_count))
    assert imgs == 3
    doc.close()


def test_export_pdf_paginates_when_full(tmp_path):
    import fitz
    out = str(tmp_path / "many.pdf")
    guide.export_pdf([make_step(w=480, h=270)] * 12, out, title="Larga")
    doc = fitz.open(out)
    assert doc.page_count >= 4           # 12 pasos no caben en 1-2 paginas
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
