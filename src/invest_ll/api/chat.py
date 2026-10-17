"""Pestaña Chat: hablar con Claude sobre TU situación. Lee y explica; no puede ejecutar nada.

Usa el CLI de `claude` con la suscripción del operador (igual que `invest-ll-generate`), así que
cada mensaje gasta cuota. El contexto (cartera, triggers, mercado con sus fechas) se reconstruye en
cada pregunta con `build_context`; el historial vive en la sesión.

Las sesiones viven en la memoria del proceso, con un id aleatorio que devuelve la primera
respuesta. Reiniciar el panel las borra, y preguntar con un id que ya no existe es un 404: seguir
como si nada empezaría una conversación nueva haciéndola pasar por la vieja.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter

from invest_ll.api.errores import no_encontrado
from invest_ll.api.schemas import MensajeChat, PeticionChat, RespuestaChat
from invest_ll.chat.context import build_context
from invest_ll.chat.session import ChatSession

router = APIRouter()

MAX_SESIONES = 50
"""Las más antiguas se olvidan: el panel es de una persona, no un servicio de chat."""

_sesiones: OrderedDict[str, tuple[ChatSession, threading.Lock]] = OrderedDict()
_cerrojo = threading.Lock()


def nueva_sesion() -> ChatSession:
    """Una conversación nueva con el CLI de claude. Los tests la sustituyen: gasta cuota."""
    return ChatSession()


def _autor(autor: str) -> Literal["operador", "claude"]:
    return "operador" if autor == "operador" else "claude"


def _buscar(id_sesion: str) -> tuple[ChatSession, threading.Lock]:
    with _cerrojo:
        encontrada = _sesiones.get(id_sesion)
        if encontrada is None:
            raise no_encontrado(
                f"no existe la sesion de chat {id_sesion!r}: las sesiones viven en memoria y se "
                "pierden al reiniciar el panel. Empieza una nueva sin sesion."
            )
        _sesiones.move_to_end(id_sesion)
        return encontrada


def _guardar(sesion: ChatSession, cerrojo: threading.Lock) -> str:
    id_sesion = secrets.token_urlsafe(16)
    with _cerrojo:
        _sesiones[id_sesion] = (sesion, cerrojo)
        while len(_sesiones) > MAX_SESIONES:
            _sesiones.popitem(last=False)
    return id_sesion


@router.post("/chat", tags=["chat"])
def chat(peticion: PeticionChat) -> RespuestaChat:
    """Pregunta a Claude con tu situación delante (gasta cuota). No puede ejecutar nada."""
    if peticion.sesion is None:
        sesion, cerrojo, id_sesion = nueva_sesion(), threading.Lock(), None
    else:
        sesion, cerrojo = _buscar(peticion.sesion)
        id_sesion = peticion.sesion

    # Un mensaje cada vez por conversacion: dos a la vez mezclarian el historial.
    with cerrojo:
        respuesta = sesion.ask(peticion.pregunta, contexto=build_context())

    # La sesion nueva solo se guarda si la primera pregunta salio bien: si claude no responde,
    # no hay conversacion que continuar.
    if id_sesion is None:
        id_sesion = _guardar(sesion, cerrojo)

    return RespuestaChat(
        sesion=id_sesion,
        respuesta=respuesta,
        historial=[MensajeChat(autor=_autor(a), texto=t) for a, t in sesion.history],
    )
