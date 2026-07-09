"""Lanzador de GuiaClick."""

from __future__ import annotations


def _set_dpi_awareness() -> None:
    # per-monitor v2: el cursor y las capturas usan pixeles fisicos -> coinciden.
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
        except Exception:  # noqa: BLE001
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:  # noqa: BLE001
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    _set_dpi_awareness()
    from guiaclick.app import main as run
    run()


if __name__ == "__main__":
    main()
