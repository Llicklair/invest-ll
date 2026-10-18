"""Los movimientos de los bots según ocurren: el feed «Ahora mismo» (docs/panel-v5.md §3 y §4).

Un movimiento es una operación (compra o venta, con su resultado si es una venta) o un evento
(arranque, parada, error, hueco, nota). El motor guarda los últimos en memoria con un número de
orden creciente: el stream (`GET /api/vivo/stream`, canal `actividad`) manda a cada cliente los
que aún no ha visto. Al abrir el panel se rellenan con lo que hay en disco, así que el feed no
empieza vacío.

El `id` de cada movimiento sale de lo que es (bot, hora, tipo…), no del número de orden: es el
mismo al reabrir el panel, y el navegador puede juntar lo que ya tenía sin repetirlo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:  # pragma: no cover
    from datetime import datetime
    from decimal import Decimal

    from invest_ll.bots.registro import Evento, ModoBot, Operacion

TipoMovimiento = Literal[
    "compra",
    "venta",
    "arranque",
    "parada",
    "error",
    "hueco",
    "info",
    "limite",
    "desconocido",
    "conciliacion",
    "real",
]

MAX_ACTIVIDAD: Final = 500
"""Los que se guardan en memoria, de todos los bots."""
AL_ABRIR_POR_BOT: Final = 60
"""Los de cada bot que se leen de disco al abrir el panel."""


@dataclass(frozen=True, slots=True)
class Movimiento:
    id: str
    at: datetime
    bot_id: str
    bot_nombre: str
    tipo: TipoMovimiento
    texto: str
    coin: str | None = None
    cantidad: Decimal | None = None
    precio: Decimal | None = None
    importe: Decimal | None = None
    comision: Decimal | None = None
    resultado: Decimal | None = None
    """Lo que ganó o perdió una venta (`metricas.resultado_venta`); None en lo demás."""
    modo: ModoBot = "ficticio"
    """El del bot cuando pasó: al activar el dinero real, lo de antes sigue siendo ficticio."""


def de_operacion(
    bot_id: str,
    bot_nombre: str,
    o: Operacion,
    resultado: Decimal | None,
    modo: ModoBot = "ficticio",
) -> Movimiento:
    return Movimiento(
        id=f"op:{bot_id}:{o.at.isoformat()}:{o.coin}:{o.lado}",
        at=o.at,
        bot_id=bot_id,
        bot_nombre=bot_nombre,
        tipo=o.lado,
        texto=o.motivo,
        coin=o.coin,
        cantidad=o.cantidad,
        precio=o.precio,
        importe=o.importe,
        comision=o.comision,
        resultado=resultado,
        modo=modo,
    )


def de_evento(bot_id: str, bot_nombre: str, e: Evento, modo: ModoBot = "ficticio") -> Movimiento:
    huella = hashlib.sha1(e.texto.encode(), usedforsecurity=False).hexdigest()[:8]
    return Movimiento(
        id=f"ev:{bot_id}:{e.at.isoformat()}:{e.tipo}:{huella}",
        at=e.at,
        bot_id=bot_id,
        bot_nombre=bot_nombre,
        tipo=e.tipo,
        texto=e.texto,
        modo=modo,
    )
