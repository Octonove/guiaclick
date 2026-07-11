"""Construccion de la guia: anota cada captura (resaltado del clic + numero),
difumina zonas sensibles y exporta a HTML, Markdown o PDF. Funciones puras
(reciben pasos/parametros, devuelven texto/bytes o escriben ficheros)."""

from __future__ import annotations

import base64
import html
import io
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class GuideError(Exception):
    pass


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = (color or "#CE6E61").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 206, 110, 97


def clean_window_title(title: str) -> str:
    """Limpia el titulo de ventana para usarlo en el texto del paso."""
    t = (title or "").strip()
    # quita sufijos tipo " - Google Chrome", " — Mozilla Firefox", " - Bloc de notas"
    t = re.split(r"\s[\-—–\|]\s", t)[0].strip()
    return t


def auto_title(step, index: int) -> str:
    win = clean_window_title(step.window)
    accion = "Haz clic derecho" if step.button == "right" else "Haz clic"
    if win:
        return f"{accion} en «{win}»"
    return f"{accion} (paso {index})"


def _apply_blur(img, regions, strength: int):
    from PIL import ImageFilter
    if not regions:
        return img
    out = img.copy()
    s = max(2, int(strength))
    for r in regions:
        try:
            x0, y0, x1, y1 = (int(v) for v in r)
        except (ValueError, TypeError):
            continue
        x0, x1 = sorted((max(0, x0), min(img.width, x1)))
        y0, y1 = sorted((max(0, y0), min(img.height, y1)))
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        region = out.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(s))
        out.paste(region, (x0, y0))
    return out


def render_step(step, index: int, *, highlight_color: str = "#CE6E61",
                blur_strength: int = 14, max_width: int = 1600):
    """Devuelve una imagen PIL anotada: difuminado + resaltado del clic + numero."""
    from PIL import Image, ImageDraw
    img = _apply_blur(step.image, step.blur, blur_strength).convert("RGB")
    x, y = int(step.x), int(step.y)

    scale = 1.0
    if max_width and img.width > max_width:
        scale = max_width / img.width
        img = img.resize((max_width, max(1, int(img.height * scale))))
        x, y = int(x * scale), int(y * scale)

    draw = ImageDraw.Draw(img, "RGBA")
    rgb = _hex_to_rgb(highlight_color)
    r = max(16, int(img.width * 0.018))
    # halo translucido + anillo
    draw.ellipse([x - r * 1.7, y - r * 1.7, x + r * 1.7, y + r * 1.7],
                 fill=rgb + (60,))
    for w, col in ((6, (255, 255, 255, 235)), (3, rgb + (255,))):
        draw.ellipse([x - r, y - r, x + r, y + r], outline=col, width=w)
    # numero del paso en una insignia
    badge = max(16, int(r * 0.95))
    bx, by = x + r, y - r - badge
    bx = min(bx, img.width - badge * 2)
    by = max(2, by)
    draw.ellipse([bx, by, bx + badge * 2, by + badge * 2], fill=rgb + (255,))
    _draw_centered_number(draw, str(index), bx, by, badge)
    return img


def _draw_centered_number(draw, text: str, bx: int, by: int, badge: int) -> None:
    from PIL import ImageFont
    font = None
    for fp in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            font = ImageFont.truetype(fp, int(badge * 1.2))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    cx, cy = bx + badge, by + badge
    try:
        l, t, rr, b = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (rr - l) / 2, cy - (b - t) / 2 - t), text, fill=(255, 255, 255, 255), font=font)
    except Exception:  # noqa: BLE001
        draw.text((cx - badge / 2, cy - badge / 2), text, fill=(255, 255, 255, 255), font=font)


def _png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def title_or_auto(step, index: int) -> str:
    return step.title.strip() if step.title.strip() else auto_title(step, index)


def _md_escape(s: str) -> str:
    """Escapa caracteres especiales de Markdown para no romper la estructura."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", s or "").replace("\n", " ")


# ----------------------------------------------------------------- export
_HTML_TPL = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
 body{{font-family:'Segoe UI',system-ui,sans-serif;color:#1E293B;max-width:880px;margin:32px auto;padding:0 20px;line-height:1.55}}
 h1{{color:#1E3A5F;border-bottom:3px solid #CE6E61;padding-bottom:8px}}
 .step{{margin:26px 0;padding-bottom:18px;border-bottom:1px solid #E2E8F0}}
 .num{{display:inline-block;background:#CE6E61;color:#fff;width:26px;height:26px;border-radius:50%;
       text-align:center;line-height:26px;font-weight:700;margin-right:8px}}
 .st{{color:#1E3A5F;font-weight:600;font-size:17px}}
 .note{{color:#475569;margin:4px 0 8px 34px}}
 img{{max-width:100%;border:1px solid #E2E8F0;border-radius:8px;display:block;margin-top:8px}}
 .meta{{color:#64748B;font-size:13px}}
 footer{{color:#94A3B8;font-size:12px;margin-top:28px}}
</style></head><body>
<h1>{title}</h1>
<div class="meta">{intro}</div>
{steps}
<footer>Generado con GuiaClick · 100% en local</footer>
</body></html>"""


def export_html(steps, out_path: str, *, title: str = "Guia", intro: str = "",
                highlight_color: str = "#CE6E61", blur_strength: int = 14) -> str:
    blocks = []
    for i, step in enumerate(steps, 1):
        img = render_step(step, i, highlight_color=highlight_color, blur_strength=blur_strength)
        b64 = base64.b64encode(_png_bytes(img)).decode("ascii")
        st = html.escape(title_or_auto(step, i))
        note = f'<div class="note">{html.escape(step.note)}</div>' if step.note.strip() else ""
        blocks.append(f'<div class="step"><div class="st"><span class="num">{i}</span>{st}</div>'
                      f'{note}<img src="data:image/png;base64,{b64}" alt="Paso {i}"></div>')
    content = _HTML_TPL.format(title=html.escape(title), intro=html.escape(intro),
                              steps="\n".join(blocks))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(content, encoding="utf-8")
    return out_path


def export_markdown(steps, out_path: str, *, title: str = "Guia", intro: str = "",
                    highlight_color: str = "#CE6E61", blur_strength: int = 14) -> str:
    out = Path(out_path)
    img_dir = out.with_suffix("")
    img_dir = img_dir.parent / (img_dir.name + "_imagenes")
    img_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    if intro.strip():
        lines += [intro.strip(), ""]
    for i, step in enumerate(steps, 1):
        img = render_step(step, i, highlight_color=highlight_color, blur_strength=blur_strength)
        name = f"paso_{i:02d}.png"
        img.save(img_dir / name)
        lines.append(f"## {i}. {_md_escape(title_or_auto(step, i))}")
        if step.note.strip():
            lines.append(_md_escape(step.note.strip()))
        lines.append(f"![Paso {i}]({img_dir.name}/{name})")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


def _rgb01(color: str) -> tuple[float, float, float]:
    r, g, b = _hex_to_rgb(color)
    return r / 255, g / 255, b / 255


def _safe_hex(color: str) -> str:
    """Devuelve un color #RRGGBB valido para CSS (o el terracota por defecto)."""
    c = (color or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c
    if re.fullmatch(r"#[0-9a-fA-F]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return "#CE6E61"


def _measure_html(html_str: str, width: float) -> float:
    """Alto (pt) que ocupa `html_str` al fluir en `width`, medido en una pagina
    scratch. Fiable: insert_htmlbox respeta las metricas reales de la fuente, a
    diferencia de estimar el alto a mano (que hacia que un titulo desbordase su
    caja y PyMuPDF lo descartara en silencio)."""
    import fitz
    d = fitz.open()
    try:
        pg = d.new_page(width=width + 2 * 40, height=4000)
        spare, _ = pg.insert_htmlbox(fitz.Rect(0, 0, width, 4000), html_str)
        return max(1.0, 4000 - spare)
    finally:
        d.close()


def _step_html(num: int, title: str, note: str, *, accent: str) -> str:
    """Bloque HTML de un paso: numero (en color de acento) + titulo en negrita +
    nota opcional en gris. Se dibuja con insert_htmlbox (nunca se recorta)."""
    t = html.escape(title)
    note_html = ""
    if note:
        n = html.escape(note).replace("\n", "<br>")
        note_html = (f'<div style="font-family:sans-serif;font-size:10px;color:#4d5a6b;'
                     f'line-height:1.35;margin-top:3px">{n}</div>')
    return (f'<div style="font-family:sans-serif;font-size:13px;line-height:1.3">'
            f'<span style="font-weight:bold;color:{accent}">{num}. </span>'
            f'<span style="font-weight:bold;color:#1e3a5f">{t}</span>{note_html}</div>')


def export_pdf(steps, out_path: str, *, title: str = "Guia", intro: str = "",
               highlight_color: str = "#CE6E61", blur_strength: int = 14) -> str:
    """PDF con layout FLUIDO: los pasos se colocan uno tras otro y solo se salta
    de pagina cuando el siguiente no cabe. (Antes cada paso iba en su propia
    pagina A4 y una captura 16:9 dejaba ~56% de la pagina en blanco.)

    El texto se dibuja con insert_htmlbox, que refluye respetando las metricas
    reales de la fuente: asi el TITULO de cada paso siempre se renderiza (con
    insert_textbox y un alto calculado a mano, los titulos podian desbordar la
    caja y descartarse en silencio)."""
    import fitz
    if not steps:
        raise GuideError("No hay pasos para exportar.")
    accent = _safe_hex(highlight_color)
    doc = fitz.open()
    try:
        PW, PH, M = 595, 842, 40      # A4 en puntos, margen
        TW = PW - 2 * M               # ancho util de texto/imagen
        MAX_IMG_H = 330               # tope de alto por imagen: caben ~2 pasos 16:9 por pagina
        GAP = 18                      # aire entre pasos
        GAP_TI = 6                    # aire entre el titulo del paso y su imagen

        page = doc.new_page(width=PW, height=PH)
        y = M
        # titulo como encabezado de la primera pagina (no portada suelta)
        title_html = (f'<div style="font-family:sans-serif;font-size:22px;font-weight:bold;'
                      f'color:#1e3a5f;line-height:1.15">{html.escape(title)}</div>')
        th = _measure_html(title_html, TW)
        page.insert_htmlbox(fitz.Rect(M, y, PW - M, y + th + 2), title_html)
        y += th + 2
        if intro.strip():
            intro_html = (f'<div style="font-family:sans-serif;font-size:11px;color:#4d5a6b;'
                          f'line-height:1.4">{html.escape(intro.strip())}</div>')
            ih = _measure_html(intro_html, TW)
            page.insert_htmlbox(fitz.Rect(M, y, PW - M, y + ih + 2), intro_html)
            y += ih + 2
        # linea separadora bajo el encabezado (como en el HTML)
        page.draw_line(fitz.Point(M, y + 3), fitz.Point(PW - M, y + 3),
                       color=_rgb01(highlight_color), width=1.5)
        y += 13

        for i, step in enumerate(steps, 1):
            img = render_step(step, i, highlight_color=highlight_color,
                              blur_strength=blur_strength)
            block = _step_html(i, title_or_auto(step, i), step.note.strip(), accent=accent)
            text_h = _measure_html(block, TW)
            ratio = min(TW / img.width, MAX_IMG_H / img.height)
            img_w, img_h = img.width * ratio, img.height * ratio
            block_h = text_h + GAP_TI + img_h + GAP

            # salto de pagina solo si el bloque no cabe (y no es lo primero de la pagina)
            if y + block_h > PH - M and y > M + 1:
                page = doc.new_page(width=PW, height=PH)
                y = M
            # bloque mas alto que una pagina entera (imagen muy vertical): reescala
            if block_h > PH - 2 * M:
                extra = block_h - (PH - 2 * M)
                img_h = max(80, img_h - extra)
                img_w = img.width * (img_h / img.height)

            # Acota la caja del texto al borde de pagina: si un titulo/nota fuese mas
            # alto que la pagina, insert_htmlbox lo ESCALA para que quepa en vez de
            # dibujar la parte inferior fuera del media box (que se perderia sin
            # aviso, justo el fallo que esta version corrige).
            text_bottom = min(y + text_h + 2, PH - M)
            if y + text_h + 2 > PH - M:
                logger.warning("Paso %d: el texto no cabe en una pagina; se reescala.", i)
            page.insert_htmlbox(fitz.Rect(M, y, PW - M, text_bottom), block)
            y = text_bottom + GAP_TI
            x0 = M + (TW - img_w) / 2
            page.insert_image(fitz.Rect(x0, y, x0 + img_w, y + img_h),
                              stream=_png_bytes(img))
            y += img_h + GAP

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()
    return out_path
