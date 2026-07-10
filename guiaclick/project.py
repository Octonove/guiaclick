"""Guardar y abrir guias como proyecto (.guiaclick): un zip con guide.json y
las capturas en PNG. Permite cerrar la app y terminar la guia en otra ocasion.
Tambien da soporte al autoguardado de sesion (recuperacion al abrir)."""

from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

from .capture import Step

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
EXT = ".guiaclick"


class ProjectError(Exception):
    pass


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_project(path, steps: list[Step], title: str = "") -> str:
    """Serializa la guia completa (incluido el estado de recorte para poder
    restaurar el original tras reabrir)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"version": FORMAT_VERSION, "title": title, "steps": []}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for i, st in enumerate(steps, 1):
            entry = {
                "img": f"paso_{i:03d}.png",
                "x": int(st.x), "y": int(st.y),
                "window": st.window, "button": st.button,
                "title": st.title, "note": st.note,
                "blur": [list(map(int, r)) for r in st.blur],
            }
            z.writestr(entry["img"], _png(st.image))
            if st.original is not None:
                oimg, ox, oy, oblur = st.original
                entry["orig"] = {"img": f"orig_{i:03d}.png", "x": int(ox), "y": int(oy),
                                 "blur": [list(map(int, r)) for r in oblur]}
                z.writestr(entry["orig"]["img"], _png(oimg))
            manifest["steps"].append(entry)
        z.writestr("guide.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return str(path)


def load_project(path) -> tuple[list[Step], str]:
    """Devuelve (steps, title). Lanza ProjectError si el archivo no es valido."""
    from PIL import Image
    path = Path(path)
    try:
        with zipfile.ZipFile(path, "r") as z:
            manifest = json.loads(z.read("guide.json").decode("utf-8"))
            if int(manifest.get("version", 0)) > FORMAT_VERSION:
                raise ProjectError("Este proyecto es de una version mas nueva de GuiaClick.")
            steps: list[Step] = []
            for e in manifest.get("steps", []):
                img = Image.open(io.BytesIO(z.read(e["img"])))
                img.load()
                st = Step(image=img, x=int(e.get("x", 0)), y=int(e.get("y", 0)),
                          window=e.get("window", ""), button=e.get("button", "left"),
                          title=e.get("title", ""), note=e.get("note", ""),
                          blur=[tuple(r) for r in e.get("blur", [])])
                o = e.get("orig")
                if o:
                    oimg = Image.open(io.BytesIO(z.read(o["img"])))
                    oimg.load()
                    st.original = (oimg, int(o.get("x", 0)), int(o.get("y", 0)),
                                   [tuple(r) for r in o.get("blur", [])])
                steps.append(st)
            return steps, str(manifest.get("title", ""))
    except ProjectError:
        raise
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError, ValueError) as exc:
        raise ProjectError(f"No se pudo abrir el proyecto: {exc}") from exc


# --------------------------------------------------------- autoguardado sesion
def autosave_path(data_dir) -> Path:
    return Path(data_dir) / f"autoguardado{EXT}"


def autosave(data_dir, steps: list[Step], title: str = "") -> None:
    """Guarda (o limpia) la sesion actual sin molestar al usuario."""
    p = autosave_path(data_dir)
    try:
        if steps:
            save_project(p, steps, title)
        else:
            p.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Autoguardado fallo: %s", exc)


def load_autosave(data_dir) -> tuple[list[Step], str] | None:
    """Devuelve la sesion autoguardada si existe y es valida; si no, None."""
    p = autosave_path(data_dir)
    if not p.exists():
        return None
    try:
        return load_project(p)
    except ProjectError as exc:
        logger.warning("Autoguardado corrupto (se ignora): %s", exc)
        return None


def clear_autosave(data_dir) -> None:
    try:
        autosave_path(data_dir).unlink(missing_ok=True)
    except OSError:
        pass
