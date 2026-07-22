"""Capa de IA local OPCIONAL via Ollama: shim del nucleo compartido
(octonove_core.llm) + las ayudas de redaccion propias de GuiaClick.
Defaults de generate: 120 s / temp 0.3 (los del core)."""

from __future__ import annotations

from octonove_core.llm import (  # noqa: F401
    OLLAMA_URL,
    _cache,
    _get,
    _resolve_ollama_url,
    available,
    default_model,
    generate,
    has_gpu,
    list_models,
    recommend_model,
    reset_cache,
    set_model,
    system_ram_gb,
)

# --- ayudas especificas de GuiaClick ----------------------------------------
# CORRECTOR, no reescritor: un modelo local 8B, ante texto muy escueto, INVENTA
# (p.ej. "Clic aqui" -> "Haz clic en «Continuar»"), lo cual en una guia es peor
# que el original. Por eso el prompt corrige redaccion sin anadir informacion y
# deja casi igual lo que ya esta claro; la temperatura es baja (0.1).
_SYS_FIX = (
    "Eres un corrector de estilo de guias paso a paso en espanol. Mejora la redaccion del "
    "texto: corrige ortografia y gramatica y hazlo claro, breve e imperativo. PROHIBIDO "
    "anadir informacion nueva o inventar botones, menus, nombres o pasos que no aparezcan "
    "en el texto. Si el texto ya es una instruccion clara, devuelvelo casi igual. Responde "
    "SOLO con el texto corregido, sin comillas, sin etiquetas y sin explicaciones.")


def polish_title(text: str, model: str | None = None) -> str | None:
    """Corrige el TITULO/instruccion de un paso (una sola linea, sin inventar nada)."""
    if not text.strip() or not available():
        return None
    out = generate(f"Corrige la redaccion de este texto de un paso, sin inventar nada:"
                   f"\n\n{text.strip()}", system=_SYS_FIX, model=model, temperature=0.1)
    if not out:
        return None
    # el titulo es de una sola linea: quita comillas envolventes y saltos
    line = out.strip().splitlines()[0].strip().strip('"').strip()
    return line or None


def polish_note(text: str, title: str = "", model: str | None = None) -> str | None:
    """Corrige la NOTA/descripcion de un paso (solo si tiene texto). Puede ser
    multilinea. `title` se pasa como contexto para no perder el sentido."""
    if not text.strip() or not available():
        return None
    ctx = f"\n(instruccion del paso: {title.strip()})" if title.strip() else ""
    out = generate(f"Corrige la redaccion de esta nota de un paso, sin inventar nada:"
                   f"\n\n{text.strip()}{ctx}", system=_SYS_FIX, model=model, temperature=0.1)
    return (out or "").strip().strip('"').strip() or None


def polish_step(text: str, model: str | None = None) -> str | None:
    """Compat: corrige solo el titulo (por si lo usa codigo antiguo)."""
    return polish_title(text, model=model)
