"""Grabador de clics global: en cada clic captura la pantalla, la posicion del
cursor y el titulo de la ventana activa. Todo local, sin hooks complejos: sondea
el estado del boton con GetAsyncKeyState (no necesita bombear mensajes)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32
    WIN = True
    # OBLIGATORIO en Python 64-bit: sin esto, GetForegroundWindow devuelve un HWND
    # truncado a 32 bits -> el titulo sale vacio y el filtro de la barra falla.
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAncestor.restype = wintypes.HWND
    _user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
except Exception as exc:  # noqa: BLE001
    WIN = False
    logger.warning("API de Windows no disponible: %s", exc)


def root_hwnd(hwnd) -> int:
    """HWND de la ventana de primer nivel (Tk envuelve sus ventanas: winfo_id da
    la hija). GA_ROOT = 2."""
    if not WIN or not hwnd:
        return int(hwnd or 0)
    try:
        return int(_user32.GetAncestor(int(hwnd), 2) or hwnd)
    except Exception:  # noqa: BLE001
        return int(hwnd)


# WDA_EXCLUDEFROMCAPTURE (0x11): Windows deja la ventana visible en pantalla pero
# la OMITE de cualquier captura/grabacion. Es justo el caso de uso previsto por
# Microsoft para barras de control de grabacion. Requiere Windows 10 2004+.
WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(hwnd) -> bool:
    """Hace que la ventana `hwnd` no aparezca en las capturas de mss. Devuelve
    True si la API lo acepto (en Windows viejos falla y se devuelve False:
    entonces la barra sigue viendose, como antes)."""
    if not WIN or not hwnd:
        return False
    try:
        return bool(_user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE))
    except Exception as exc:  # noqa: BLE001
        logger.debug("SetWindowDisplayAffinity no disponible: %s", exc)
        return False

try:
    import mss
    from PIL import Image
    CAP_OK = True
except Exception as exc:  # noqa: BLE001
    CAP_OK = False
    logger.warning("Captura de pantalla no disponible (mss/Pillow): %s", exc)

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02

AVAILABLE = WIN and CAP_OK


@dataclass
class Step:
    image: "Image.Image"          # captura de pantalla del monitor del clic
    x: int                         # posicion del clic relativa a la imagen
    y: int
    window: str = ""              # titulo de la ventana activa
    button: str = "left"
    title: str = ""               # texto del paso (editable)
    note: str = ""                # descripcion adicional (editable)
    blur: list = field(default_factory=list)   # zonas a difuminar [(x0,y0,x1,y1)] en coords de imagen
    original: tuple | None = None  # (image, x, y, blur) antes del primer recorte, para restaurar


def crop_step(step: Step, box: tuple[int, int, int, int], min_side: int = 40) -> bool:
    """Recorta la imagen del paso a `box` (coords de imagen), ajustando el punto
    del clic y las zonas difuminadas. Guarda el estado previo en step.original
    (solo la primera vez) para poder restaurar. Devuelve False si el recorte es
    demasiado pequeno o queda fuera de la imagen."""
    x0 = max(0, min(int(box[0]), int(box[2])))
    y0 = max(0, min(int(box[1]), int(box[3])))
    x1 = min(step.image.width, max(int(box[0]), int(box[2])))
    y1 = min(step.image.height, max(int(box[1]), int(box[3])))
    if (x1 - x0) < min_side or (y1 - y0) < min_side:
        return False
    if step.original is None:
        step.original = (step.image, step.x, step.y, list(step.blur))
    step.image = step.image.crop((x0, y0, x1, y1))
    step.x = max(0, min(step.image.width - 1, step.x - x0))
    step.y = max(0, min(step.image.height - 1, step.y - y0))
    new_blur = []
    for bx0, by0, bx1, by1 in step.blur:
        nx0, ny0 = max(0, bx0 - x0), max(0, by0 - y0)
        nx1 = min(step.image.width, bx1 - x0)
        ny1 = min(step.image.height, by1 - y0)
        if nx1 - nx0 >= 4 and ny1 - ny0 >= 4:   # conserva solo lo que sigue visible
            new_blur.append((nx0, ny0, nx1, ny1))
    step.blur = new_blur
    return True


def restore_step(step: Step) -> bool:
    """Deshace el recorte: vuelve a la imagen/clic/difuminados originales."""
    if step.original is None:
        return False
    step.image, step.x, step.y, blur = step.original
    step.blur = list(blur)
    step.original = None
    return True


def _cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(pt)):
        return 0, 0
    return int(pt.x), int(pt.y)


def _foreground_title() -> tuple[int, str]:
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return 0, ""
    length = max(0, _user32.GetWindowTextLengthW(hwnd))   # -1 en error -> 0
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return int(hwnd), buf.value


def _down(vk: int) -> bool:
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)


class ClickRecorder:
    """Captura un paso por cada clic mientras esta grabando."""

    def __init__(self, *, capture_right: bool = False, ignore_hwnds=None,
                 ignore_titles=None):
        self.capture_right = capture_right
        # callable -> set de hwnds a ignorar (la propia barra de GuiaClick)
        self.ignore_hwnds = ignore_hwnds or (lambda: set())
        # callable -> set de titulos a ignorar (respaldo por si el hwnd no coincide)
        self.ignore_titles = ignore_titles or (lambda: set())
        self.steps: list[Step] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        # dedupe de doble clic: el 2º clic en el mismo sitio en <450 ms no crea paso
        self._last_click = (0.0, 0, 0, "")   # (t, x, y, button)

    def start(self) -> None:
        if not AVAILABLE:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def count(self) -> int:
        with self._lock:
            return len(self.steps)

    def _run(self) -> None:
        try:
            sct = mss.mss()
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo iniciar la captura: %s", exc)
            return
        buttons = [(VK_LBUTTON, "left")]
        if self.capture_right:
            buttons.append((VK_RBUTTON, "right"))
        prev = {vk: False for vk, _ in buttons}
        try:
            while not self._stop.is_set():
                for vk, name in buttons:
                    now = _down(vk)
                    if now and not prev[vk]:
                        self._capture(sct, name)
                    prev[vk] = now
                time.sleep(0.015)
        finally:
            try:
                sct.close()
            except Exception:  # noqa: BLE001
                pass

    def _capture(self, sct, button: str) -> None:
        try:
            cx, cy = _cursor_pos()
            hwnd, title = _foreground_title()
            if hwnd in self.ignore_hwnds() or title in self.ignore_titles():
                return     # clic en la propia barra de GuiaClick: no es un paso
            # Doble clic = un solo paso: el 2º clic casi en el mismo punto y en
            # <450 ms duplicaria la captura sin aportar nada.
            now = time.time()
            lt, lx, ly, lb = self._last_click
            self._last_click = (now, cx, cy, button)
            if button == lb and (now - lt) < 0.45 and abs(cx - lx) <= 8 and abs(cy - ly) <= 8:
                return
            mon = self._monitor_at(sct, cx, cy)
            grab = sct.grab(mon)
            img = Image.frombytes("RGB", grab.size, grab.bgra, "raw", "BGRX")
            rel_x = max(0, min(img.width - 1, cx - mon["left"]))
            rel_y = max(0, min(img.height - 1, cy - mon["top"]))
            step = Step(image=img, x=rel_x, y=rel_y, window=title, button=button)
            with self._lock:
                self.steps.append(step)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Captura de clic fallo: %s", exc)

    @staticmethod
    def _monitor_at(sct, x: int, y: int) -> dict:
        # sct.monitors[0] = todo el escritorio virtual; [1..] = monitores fisicos
        physical = sct.monitors[1:] or [sct.monitors[0]]
        for mon in physical:
            if mon["left"] <= x < mon["left"] + mon["width"] and \
               mon["top"] <= y < mon["top"] + mon["height"]:
                return mon
        # borde exacto o fuera: el monitor fisico mas cercano (no el escritorio
        # virtual entero, que daria una captura enorme y descuadrada).
        def dist(m):
            cx = min(max(x, m["left"]), m["left"] + m["width"] - 1)
            cy = min(max(y, m["top"]), m["top"] + m["height"] - 1)
            return (cx - x) ** 2 + (cy - y) ** 2
        return min(physical, key=dist)

    def stop(self) -> list[Step]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            return list(self.steps)
