"""Configuracion y rutas de datos de GuiaClick (shim del nucleo compartido
octonove_core.config)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from octonove_core.config import default_documents_dir as _default_documents_dir
from octonove_core.config import get_data_dir as _get_data_dir
from octonove_core.config import load_config as _load_config
from octonove_core.config import save_config as _save_config
from octonove_core.config import setup_logging as _setup_logging

from . import APP_NAME

logger = logging.getLogger(__name__)


def get_data_dir():
    return _get_data_dir(APP_NAME)


def default_output_dir() -> Path:
    return _default_documents_dir(APP_NAME)


CONFIG_PATH = get_data_dir() / "config.json"
LOG_PATH = get_data_dir() / "guiaclick.log"


@dataclass
class AppConfig:
    output_dir: str = field(default_factory=lambda: str(default_output_dir()))
    highlight_color: str = "#CE6E61"     # color del resaltado del clic
    capture_right_click: bool = False    # tambien capturar clic derecho
    auto_title_from_window: bool = True   # texto del paso a partir del titulo de ventana
    blur_strength: int = 14
    seen_welcome: bool = False

    def ensure_dirs(self) -> None:
        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("No se pudo crear %s: %s", self.output_dir, exc)


def load_config() -> AppConfig:
    return _load_config(CONFIG_PATH, AppConfig)


def save_config(cfg: AppConfig) -> None:
    _save_config(cfg, CONFIG_PATH)


def setup_logging() -> None:
    _setup_logging(LOG_PATH)
