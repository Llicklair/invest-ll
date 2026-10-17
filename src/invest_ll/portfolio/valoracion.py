"""Cuánto vale hoy lo que tienes, con la fecha del precio y sin inventar lo que falta.

Para la cifra grande de Inicio ("Tu dinero hoy") y para el resumen del plan por partes:

- `valor`: lo que valen las posiciones al último cierre, más el efectivo si es positivo. Un
  efectivo derivado negativo significa que faltan depósitos por anotar (`derive`), no que debas
  dinero: sumarlo restaría de tu patrimonio algo que no existe.
- `puesto`: lo que costó lo que tienes (comisiones incluidas), más ese mismo efectivo.
- `ganancia`: lo que ganarías o perderías si vendieras hoy. Si falta el precio de algo, `valor`
  y `ganancia` son `None` e `incompleto` lo dice: un total sin una de sus partes es inventado.
- `fecha_precios`: la del precio MÁS ANTIGUO usado; la cifra no es más reciente que eso.

Pura: recibe la cartera derivada y una función de precios.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.portfolio.models import CERO

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.portfolio.derive import Portfolio

Precio = tuple[Decimal, date]


@dataclass(frozen=True, slots=True)
class Valoracion:
    valor: Decimal | None
    puesto: Decimal
    ganancia: Decimal | None
    ganancia_pct: float | None
    realizado: Decimal
    fecha_precios: date | None
    incompleto: bool


def valorar(
    cartera: Portfolio,
    precio: Callable[[str], Precio | None],
    *,
    solo: Callable[[str], bool] | None = None,
    con_efectivo: bool = True,
) -> Valoracion:
    """Valora las posiciones abiertas (todas, o las que acepte `solo`)."""

    def entra(simbolo: str) -> bool:
        return solo is None or solo(simbolo)

    efectivo = max(cartera.cash, CERO) if con_efectivo else CERO
    valor: Decimal | None = efectivo
    puesto = efectivo
    ganancia: Decimal | None = CERO
    fechas: list[date] = []
    realizado = sum((t.realized_pnl for t in cartera.closed_trades if entra(t.symbol)), CERO)
    for posicion in cartera.open_positions:
        if not entra(posicion.symbol):
            continue
        puesto += posicion.cost
        realizado += posicion.realized_pnl
        cierre = precio(posicion.symbol)
        if cierre is None:
            valor = ganancia = None
            continue
        fechas.append(cierre[1])
        if valor is not None and ganancia is not None:
            valor += posicion.value_at(cierre[0])
            ganancia += posicion.unrealized_at(cierre[0])
    pct = float(ganancia / puesto) if ganancia is not None and puesto > 0 else None
    return Valoracion(
        valor=valor,
        puesto=puesto,
        ganancia=ganancia,
        ganancia_pct=pct,
        realizado=realizado,
        fecha_precios=min(fechas) if fechas else None,
        incompleto=valor is None,
    )
