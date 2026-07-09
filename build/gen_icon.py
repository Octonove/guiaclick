"""Genera build/icon.ico para GuiaClick (cursor + numero sobre navy)."""

from pathlib import Path
from PIL import Image, ImageDraw

NAVY = (30, 58, 95, 255)
NAVY2 = (21, 48, 77, 255)
TERRA = (206, 110, 97, 255)
WHITE = (255, 255, 255, 255)


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=NAVY)
    d.rounded_rectangle([0, int(size * 0.5), size - 1, size - 1], radius=r, fill=NAVY2)
    # anillo de "clic" terracota
    cx, cy = int(size * 0.42), int(size * 0.55)
    rad = int(size * 0.20)
    d.ellipse([cx - rad - 3, cy - rad - 3, cx + rad + 3, cy + rad + 3], outline=WHITE, width=max(2, size // 40))
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=TERRA, width=max(2, size // 28))
    # puntero
    p = int(size * 0.30)
    pts = [(p, int(size * 0.20)), (p, int(size * 0.56)), (int(p + size * 0.10), int(size * 0.46)),
           (int(p + size * 0.16), int(size * 0.60)), (int(p + size * 0.22), int(size * 0.57)),
           (int(p + size * 0.16), int(size * 0.43)), (int(p + size * 0.27), int(size * 0.43))]
    d.polygon(pts, fill=WHITE)
    return img


def main() -> None:
    out = Path(__file__).resolve().parent / "icon.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make(s) for s in sizes]
    imgs[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes])
    make(256).save(out.with_name("icon_preview.png"))
    print("icono ->", out)


if __name__ == "__main__":
    main()
