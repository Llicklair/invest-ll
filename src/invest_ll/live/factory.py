"""Qué broker se construye para cada modo. **Un solo sitio.**

Esta decisión —simulación devuelve el que no manda nada, cualquier otro modo devuelve el que sí—
es la bisagra entre no mover dinero y moverlo. Duplicarla en el terminal y en el panel sería pedir
que un día diverjan, y la copia que se quedara atrás sería la que envía órdenes cuando no debe.

`ccxt` se importa dentro y no arriba a propósito: quien solo simula no necesita tener instalada la
librería que habla con los exchanges.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from invest_ll.live.broker import SimulatedBroker
from invest_ll.live.mode import Simulation

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.broker import Broker
    from invest_ll.live.mode import OperatingMode

EXCHANGE_POR_DEFECTO = "binance"


def construir_broker(modo: OperatingMode, *, exchange_id: str = EXCHANGE_POR_DEFECTO) -> Broker:
    """El broker que corresponde al modo.

    En `Simulation` devuelve `SimulatedBroker`, que no manda nada al exterior ni con confirmación.
    En pruebas o real devuelve el que habla con el exchange — y ese comprueba el modo otra vez al
    enviar, porque entre construirlo y usarlo puede pasar cualquier cosa.
    """
    if isinstance(modo, Simulation):
        return SimulatedBroker()

    from invest_ll.live.ccxt_broker import CcxtBroker, build_exchange

    return CcxtBroker(build_exchange(modo, exchange_id=exchange_id), mode=modo)
