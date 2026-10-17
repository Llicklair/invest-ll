"""La cabecera del panel: lo primero que hay que saber al mirar cualquier cifra.

El modo va aquí y no escondido en una pestaña. Anunciar "no ejecuta órdenes reales" cuando sí
puede sería la clase de mentira que este proyecto existe para no contar. La reserva de datos,
también: recorta los backtests, y sin decirlo un resultado de 2024 parece de hoy.
"""

from __future__ import annotations

from fastapi import APIRouter

from invest_ll.api.activos import como_activo, descargados
from invest_ll.api.schemas import Estado, Modo
from invest_ll.dashboard.data import aviso_de_reserva
from invest_ll.live.mode import Real, resolve_mode
from invest_ll.portfolio.triggers import TriggerStore

router = APIRouter()


def modo_actual() -> Modo:
    modo = resolve_mode()
    return Modo(
        nombre=modo.name, envia_ordenes=modo.sends_real_orders, es_real=isinstance(modo, Real)
    )


@router.get("/estado", tags=["estado"])
def estado() -> Estado:
    """Modo de operación, reserva de datos, activos descargados y pausa de entradas."""
    activos = [a for a in map(como_activo, descargados()) if a is not None]
    return Estado(
        modo=modo_actual(),
        reserva=aviso_de_reserva(),
        activos=activos,
        pausa=TriggerStore().halted(),
    )
