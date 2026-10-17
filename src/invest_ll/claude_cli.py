"""Dónde está el CLI de `claude` (Claude Code), que INVEST LL usa con la suscripción de Marcos.

Un solo sitio para los que lo llaman: el chat, el generador de decisiones del LLM y Diseñar con
Claude. En Windows, npm instala un `claude.cmd` que llama a un `claude.exe`; `subprocess` no
encuentra "claude" a secas (FileNotFoundError), y pasar por el .cmd estropea los argumentos con
comillas y saltos de línea. Por eso se usa el .exe directamente cuando existe.

Y su conexión (docs/panel-v5.md): `estado()` pregunta a `claude auth status --json` si hay sesión
y con qué suscripción, sin gastar cuota; `abrir_inicio_de_sesion()` abre una ventana con
`claude auth login --claudeai` para iniciarla con la suscripción (Pro, Max…). De lo que dice el CLI
solo se toma si hay sesión, cómo y qué plan: ni correo, ni organización, ni nada que identifique la
cuenta o sirva para entrar en ella.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

EJECUTABLE = "claude"
PLAZO_ESTADO: Final = 20.0
"""Segundos que se espera a `claude auth status` (arranca node: tarda un par de segundos)."""

NOMBRE_PLAN: Final[dict[str, str]] = {
    "max": "Max",
    "pro": "Pro",
    "team": "Team",
    "enterprise": "Enterprise",
}


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


@dataclass(frozen=True, slots=True)
class EstadoClaude:
    instalado: bool
    conectado: bool
    con_suscripcion: bool
    """Con la suscripción de claude.ai (y no con una clave de la API, que se paga aparte)."""
    plan: str | None
    """'Max', 'Pro'… o None si no se sabe."""
    aviso: str | None


def estado() -> EstadoClaude:
    """Si `claude` está instalado y con sesión, y con qué. Nunca lanza: lo que falle, en `aviso`."""
    ruta = ejecutable()
    if ruta is None:
        return EstadoClaude(
            False,
            False,
            False,
            None,
            "Claude Code no está instalado en este equipo. Se instala con «npm install -g "
            "@anthropic-ai/claude-code» y luego se conecta aquí.",
        )
    try:
        salida = subprocess.run(
            [ruta, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PLAZO_ESTADO,
            check=False,
        )
        crudo: object = json.loads(salida.stdout or "{}")
    except subprocess.TimeoutExpired:
        return EstadoClaude(True, False, False, None, "Claude Code no ha contestado a tiempo.")
    except (OSError, json.JSONDecodeError):
        return EstadoClaude(True, False, False, None, "No se pudo leer el estado de Claude Code.")
    datos: dict[str, object] = cast("dict[str, object]", crudo) if isinstance(crudo, dict) else {}
    if not datos.get("loggedIn"):
        return EstadoClaude(True, False, False, None, None)
    metodo = str(datos.get("authMethod") or "")
    tipo = str(datos.get("subscriptionType") or "").lower()
    suscripcion = metodo == "claude.ai"
    plan = NOMBRE_PLAN.get(tipo, tipo.capitalize() or None) if suscripcion else None
    aviso = (
        None
        if suscripcion
        else "Está conectado con una clave de la API de Anthropic, que se paga por uso: para usar "
        "tu suscripción, conéctalo con ella."
    )
    return EstadoClaude(True, True, suscripcion, plan, aviso)


def abrir_inicio_de_sesion() -> None:
    """Abre una ventana con `claude auth login --claudeai`: ahí se elige la cuenta en el
    navegador. No espera a que acabe (lo que pase se ve después con `estado()`).

    `OSError` si no se puede abrir; `FileNotFoundError` si `claude` no está instalado."""
    ruta = ejecutable()
    if ruta is None:
        raise FileNotFoundError("Claude Code no está instalado en este equipo.")
    orden = [ruta, "auth", "login", "--claudeai"]
    if sys.platform == "win32":
        # Una consola propia: el inicio de sesión pide pulsar teclas y enseña un enlace.
        subprocess.Popen(orden, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:  # pragma: no cover - el panel corre en Windows
        subprocess.Popen(orden, start_new_session=True)
