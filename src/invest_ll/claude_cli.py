"""Dónde está el CLI de `claude` (Claude Code), que INVEST LL usa con la suscripción de Marcos.

Un solo sitio para los tres que lo llaman: el chat, el generador de decisiones del LLM y Diseñar con
Claude. En Windows, npm instala un `claude.cmd` que llama a un `claude.exe`; `subprocess` no
encuentra "claude" a secas (FileNotFoundError), y pasar por el .cmd estropea los argumentos con
comillas y saltos de línea. Por eso se usa el .exe directamente cuando existe.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

EJECUTABLE = "claude"


def ejecutable() -> str | None:
    """La ruta del `claude` de verdad, o `None` si no está instalado."""
    ruta = shutil.which(EJECUTABLE)
    if ruta is None:
        return None
    p = Path(ruta)
    if sys.platform == "win32" and p.suffix.lower() != ".exe":
        nativo = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if nativo.is_file():
            return str(nativo)
    return ruta
