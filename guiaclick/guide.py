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


def _wrapped_height(text: str, width: float, fontsize: float, *,
                    fontname: str = "helv", line_factor: float = 1.32,
                    max_lines: int = 8) -> float:
    """Alto (pt) que ocupara `text` al ajustarse a `width`. Evita que un titulo o
    nota largos se corten con un rectangulo de alto fijo. Acotado a max_lines."""
    import fitz
    if not text.strip():
        return 0.0
    lines = 0
    for para in text.splitlines() or [text]:
        words = para.split()
        if not words:
            lines += 1
            continue
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if cur and fitz.get_text_length(trial, fontname=fontname, fontsize=fontsize) > width:
                lines += 1
                cur = w
            else:
                cur = trial
        if cur:
            lines += 1
    lines = max(1, min(lines, max_lines))
    return lines * fontsize * line_factor


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


def export_pdf(steps, out_path: str, *, title: str = "Guia", intro: str = "",
               highlight_color: str = "#CE6E61", blur_strength: int = 14) -> str:
    import fitz
    doc = fitz.open()
    try:
        PW, PH, M = 595, 842, 40   # A4 puntos, margen
        # portada simple
        page = doc.new_page(width=PW, height=PH)
        page.insert_textbox(fitz.Rect(M, 80, PW - M, 200), title, fontsize=24,
                            color=(0.12, 0.23, 0.37), fontname="helv")
        if intro.strip():
            page.insert_textbox(fitz.Rect(M, 150, PW - M, 320), intro.strip(),
                                fontsize=11, color=(0.3, 0.35, 0.42))
        for i, step in enumerate(steps, 1):
            img = render_step(step, i, highlight_color=highlight_color, blur_strength=blur_strength)
            png = _png_bytes(img)
            page = doc.new_page(width=PW, height=PH)
            head = f"{i}. {title_or_auto(step, i)}"
            tw = PW - 2 * M
            head_h = max(20, _wrapped_height(head, tw, 13, fontname="hebo") + 6)
            page.insert_textbox(fitz.Rect(M, M, PW - M, M + head_h), head, fontsize=13,
                                color=(0.12, 0.23, 0.37), fontname="hebo")
            top = M + head_h
            if step.note.strip():
                note = step.note.strip()
                note_h = _wrapped_height(note, tw, 10) + 6
                page.insert_textbox(fitz.Rect(M, top, PW - M, top + note_h), note,
                                    fontsize=10, color=(0.3, 0.35, 0.42))
                top += note_h
            # imagen ajustada al ancho conservando proporcion
            avail_w, avail_h = PW - 2 * M, PH - top - M
            iw, ih = img.width, img.height
            ratio = min(avail_w / iw, avail_h / ih)
            w, h = iw * ratio, ih * ratio
            x0 = M + (avail_w - w) / 2
            rect = fitz.Rect(x0, top, x0 + w, top + h)
            page.insert_image(rect, stream=png)
        if doc.page_count == 0:
            raise GuideError("No hay pasos para exportar.")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_path, garbage=3, deflate=True)
    finally:
        doc.close()
    return out_path
