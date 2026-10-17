"""De las órdenes enviadas (`ledger/orders.jsonl`) a la cartera, sin teclear nada dos veces.

Copiar a mano lo que el sistema ya sabe es justo donde se cuelan los errores. Este puente lo
automatiza con tres reglas que no se pueden desactivar:

1. **Las pruebas no entran en la cartera real.** Los precios de la red de pruebas no son los del
   mercado: mezclar su P&L con dinero de verdad corrompería el historial con el que se decide.
   Se pueden pedir a propósito (`MODOS_FICTICIOS`), para llevarlas a otra cartera. La simulación
   no entra nunca, ni pidiéndola: no salió al exterior, no hay nada que registrar.
2. **Nada se importa dos veces.** El identificador del movimiento sale de su contenido.
3. **Lo que no se ejecutó no es una compra.** Rechazadas, de estado desconocido, sin precio de
   ejecución o sin comisión conocida se quedan fuera — y se cuentan por separado, porque un
   filtro silencioso es una mentira con retraso.

Límite conocido: el registro de órdenes guarda la comisión sin su moneda. Aquí se toma en la
moneda de cotización del par (USDT en BTC/USDT), que es como se lleva el efectivo de la cartera.
Si el exchange la cobró en otra moneda (el activo comprado, BNB), el coste queda mal medido;
`invest-ll-portfolio reconciliar` es lo que lo saca a la luz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from invest_ll.live.broker import OrderStatus, Side
from invest_ll.portfolio.models import Activity, ActivityType

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable
    from collections.abc import Set as AbstractSet

    from invest_ll.live.ledger import LedgerEntry
    from invest_ll.portfolio.store import ActivityStore

# Los nombres de modo que `ExecutionLedger` guarda en cada entrada (ver live/mode.py).
MODO_REAL = "REAL"
MODO_PRUEBAS = "pruebas"
MODO_SIMULACION = "simulacion"

MODOS_REALES: frozenset[str] = frozenset({MODO_REAL})
"""Por defecto solo entra el dinero real."""
MODOS_FICTICIOS: frozenset[str] = frozenset({MODO_PRUEBAS})
"""La red de pruebas, a propósito y para otra cartera. Nunca la simulación."""


class _Descarte(Enum):
    """Por qué una orden no se convierte en movimiento."""

    SIMULACION = "simulacion"
    NO_EJECUTADA = "no ejecutada"
    DESCONOCIDA = "estado desconocido"
    SIN_PRECIO = "sin precio de ejecucion"
    SIN_COMISION = "sin comision registrada"


@dataclass(frozen=True, slots=True)
class OrderImportResult:
    """Los movimientos nuevos y la cuenta de todo lo que se quedó fuera, por motivo."""

    activities: tuple[Activity, ...]
    skipped_by_mode: int = 0
    """De otro modo que el pedido: pruebas en la cartera real, o al revés, o simulación."""
    not_executed: int = 0
    """Rechazadas o con cantidad ejecutada cero."""
    unknown_status: int = 0
    """Se enviaron y se perdió la conexión: no se sabe si se ejecutaron."""
    without_price: int = 0
    """Ejecutadas, pero sin precio de ejecución registrado."""
    without_commission: int = 0
    """Ejecutadas, pero sin comisión conocida: un cero inventado las haría más rentables."""
    already_known: int = 0
    """Ya estaban en la cartera."""

    def describe(self) -> str:
        partes = [
            f"{len(self.activities)} movimiento(s) nuevo(s) en la cartera"
            if self.activities
            else "nada nuevo que importar"
        ]
        if self.already_known:
            partes.append(f"{self.already_known} ya estaban")
        if self.skipped_by_mode:
            partes.append(f"{self.skipped_by_mode} de otro modo, que no entran en esta cartera")
        if self.not_executed:
            partes.append(f"{self.not_executed} no ejecutada(s)")
        if self.unknown_status:
            partes.append(
                f"{self.unknown_status} de ESTADO DESCONOCIDO: compruebalas en el exchange y, si "
                "se ejecutaron, registralas a mano"
            )
        if self.without_price:
            partes.append(f"{self.without_price} sin precio de ejecucion registrado")
        if self.without_commission:
            partes.append(f"{self.without_commission} sin comision registrada")
        return "; ".join(partes) + "."


def orden_a_actividad(entrada: LedgerEntry) -> Activity | None:
    """El movimiento que corresponde a una orden, o `None` si no hay nada que registrar.

    Se registra lo EJECUTADO, no lo pedido: una parcial anotada con la cantidad pedida inventaría
    una posición más grande que la real. No mira el modo: eso lo decide quien importa.
    """
    convertida = _convertir(entrada)
    return convertida if isinstance(convertida, Activity) else None


def actividades_desde_ordenes(
    entradas: Iterable[LedgerEntry],
    *,
    modos: AbstractSet[str] = MODOS_REALES,
    conocidos: AbstractSet[str] = frozenset(),
) -> OrderImportResult:
    """Convierte las órdenes de los modos pedidos, saltando lo ya conocido.

    `conocidos` son los identificadores que ya están en la cartera (`ActivityStore.known_ids()`).
    """
    if MODO_SIMULACION in modos:
        raise ValueError(
            "la simulacion nunca sale al exterior: no hay ninguna orden suya que registrar"
        )

    nuevas: list[Activity] = []
    vistos = set(conocidos)
    cuenta = dict.fromkeys(_Descarte, 0)
    por_modo = 0
    ya_estaban = 0

    for entrada in entradas:
        if entrada.mode_name not in modos:
            por_modo += 1
            continue
        convertida = _convertir(entrada)
        if isinstance(convertida, _Descarte):
            cuenta[convertida] += 1
            continue
        # Una orden repetida en el registro tampoco entra dos veces.
        if convertida.activity_id in vistos:
            ya_estaban += 1
            continue
        vistos.add(convertida.activity_id)
        nuevas.append(convertida)

    return OrderImportResult(
        activities=tuple(nuevas),
        skipped_by_mode=por_modo + cuenta[_Descarte.SIMULACION],
        not_executed=cuenta[_Descarte.NO_EJECUTADA],
        unknown_status=cuenta[_Descarte.DESCONOCIDA],
        without_price=cuenta[_Descarte.SIN_PRECIO],
        without_commission=cuenta[_Descarte.SIN_COMISION],
        already_known=ya_estaban,
    )


def importar_a_cartera(
    entradas: Iterable[LedgerEntry], almacen: ActivityStore, *, modos: AbstractSet[str]
) -> OrderImportResult:
    """Convierte las órdenes y las escribe en la cartera, con las mismas reglas de siempre.

    Es lo que hace `invest-ll-portfolio import-ledger`, en una llamada: el panel lo usa justo
    después de enviar una orden para que lo ejecutado pase solo a la cartera de su modo.
    """
    resultado = actividades_desde_ordenes(entradas, modos=modos, conocidos=almacen.known_ids())
    for actividad in resultado.activities:
        almacen.append(actividad)
    return resultado


def _convertir(entrada: LedgerEntry) -> Activity | _Descarte:
    resultado = entrada.result
    if entrada.mode_name == MODO_SIMULACION:
        return _Descarte.SIMULACION
    if resultado.status is OrderStatus.UNKNOWN:
        # No se sabe si se ejecuto: darla por buena inventaria una posicion, y darla por
        # perdida podria esconder una que si existe. Se cuenta aparte para que se mire.
        return _Descarte.DESCONOCIDA
    if resultado.status is OrderStatus.REJECTED or resultado.filled_quantity <= 0:
        return _Descarte.NO_EJECUTADA
    if resultado.fill_price is None or resultado.fill_price <= 0:
        return _Descarte.SIN_PRECIO
    if resultado.commission is None:
        return _Descarte.SIN_COMISION

    referencia = f":{resultado.broker_reference}" if resultado.broker_reference else ""
    return Activity(
        # Sin hora de ejecucion, la de registro: se apunta justo despues de ejecutar.
        timestamp=resultado.executed_at or entrada.recorded_at,
        type=ActivityType.BUY if resultado.request.side is Side.BUY else ActivityType.SELL,
        symbol=resultado.request.symbol,
        quantity=resultado.filled_quantity,
        unit_price=resultado.fill_price,
        fee=resultado.commission,
        source=f"ledger:{entrada.mode_name}{referencia}",
    )
