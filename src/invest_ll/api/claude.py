"""Claude con tu suscripción (docs/panel-v5.md): si está conectado y con qué plan, y un botón para
conectarlo.

INVEST LL usa el CLI de `claude` (Claude Code) para Pregunta, Mi plan y Diseñar con Claude, con la
suscripción de Marcos: gasta su cuota, no se paga aparte. Conectar abre una ventana en este equipo
con el inicio de sesión de Claude Code; la API solo atiende a `localhost`. Lo que se dice de la
cuenta es si hay sesión, cómo y qué plan: nada que la identifique.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll import claude_cli
from invest_ll.api.errores import conflicto, invalido
from invest_ll.api.schemas_v5 import ConectarClaude, EstadoClaude

router = APIRouter()

USOS = ["Pregunta", "Mi plan", "Diseñar con Claude", "El conector de Claude (MCP)"]


def _estado() -> EstadoClaude:
    e = claude_cli.estado()
    return EstadoClaude(
        instalado=e.instalado,
        conectado=e.conectado,
        con_suscripcion=e.con_suscripcion,
        plan=e.plan,
        aviso=e.aviso,
        usos=USOS,
    )


@router.get("/claude", tags=["claude"])
def estado() -> EstadoClaude:
    """Si Claude Code está instalado y conectado, y con qué (sin gastar cuota)."""
    return _estado()


@router.post("/claude/conectar", tags=["claude"])
def conectar() -> ConectarClaude:
    """Abre en este equipo la ventana de inicio de sesión de Claude Code con la suscripción. 409 si
    ya está conectado con ella; 422 si Claude Code no está instalado."""
    e = claude_cli.estado()
    if e.conectado and e.con_suscripcion:
        raise conflicto(
            f"Claude ya está conectado con tu suscripción{f' {e.plan}' if e.plan else ''}."
        )
    try:
        claude_cli.abrir_inicio_de_sesion()
    except FileNotFoundError as error:
        raise invalido(
            f"{error} Se instala con «npm install -g @anthropic-ai/claude-code»."
        ) from error
    except OSError as error:
        raise invalido(f"No se pudo abrir la ventana de inicio de sesión: {error}") from error
    return ConectarClaude(
        abierto=True,
        texto="Se ha abierto una ventana de Claude Code en este equipo: sigue sus pasos (abre tu "
        "navegador para elegir la cuenta) y vuelve aquí. Esta página se entera sola.",
    )
