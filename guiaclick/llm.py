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
_SYS = ("Eres un redactor tecnico. Reescribe instrucciones de una guia paso a paso "
        "para que sean claras, breves e imperativas, en espanol. Responde solo con el "
        "texto reescrito, sin comillas ni numeracion.")


def polish_step(text: str, model: str | None = None) -> str | None:
    if not text.strip() or not available():
        return None
    return generate(f"Reescribe este paso de forma clara y breve: {text}",
                    system=_SYS, model=model, temperature=0.2)
