"""Lo que el exchange dice que tienes, frente a lo que tu cartera cree.

Es la única comprobación del sistema que mira fuera. Todo lo demás deriva del registro, así que si
al registro le falta algo, sus cifras cuadran entre sí y el error no se nota nunca. El caso que la
motiva: ingresas 500 USDT en el exchange y no lo anotas; tu efectivo derivado se queda a cero y
cualquier rentabilidad sobre el capital empleado sale inflada.

**No arregla nada por su cuenta.** Dice qué falta y qué comando lo cuadraría; registrar es una
decisión del operador. Un reconciliador que ajusta solo tapa justamente el error que debía enseñar.

Solo se compara lo que has tocado: la red de pruebas reparte saldo en cientos de monedas y
enterraría lo que importa. Lo demás no se esconde: se cuenta aparte.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.portfolio.models import CERO, como_texto

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable, Mapping

MONEDAS_DE_CUENTA: frozenset[str] = frozenset({"USDT"})
"""Monedas en las que vive el efectivo de la cartera: se comparan siempre."""

MONEDA_DE_COTIZACION = "USDT"
"""Con la que se forma el par al proponer registrar un activo (BTC -> BTC/USDT), igual que las
órdenes de `invest-ll-execute`, para que el movimiento caiga en la misma posición."""

POLVO = Decimal("0.00000001")
"""Diferencia que no cuenta como descuadre: un satoshi. Por debajo es redondeo del exchange."""

MAX_NOMBRES_EN_RESUMEN = 5


@dataclass(frozen=True, slots=True)
class Diferencia:
    """Un activo cuyo saldo en el exchange no coincide con el de la cartera."""

    symbol: str
    en_el_exchange: Decimal
    en_la_cartera: Decimal

    @property
    def falta_registrar(self) -> Decimal:
        """Positivo: hay en el exchange algo que la cartera no sabe. Negativo: al revés."""
        return self.en_el_exchange - self.en_la_cartera

    @property
    def falta_en_la_cartera(self) -> bool:
        return self.falta_registrar > 0

    @property
    def es_efectivo(self) -> bool:
        return self.symbol in MONEDAS_DE_CUENTA

    def como_cuadrarlo(self) -> str:
        """El comando que lo cuadraría. Se propone; no se ejecuta."""
        cantidad = como_texto(abs(self.falta_registrar))
        if self.es_efectivo:
            if self.falta_en_la_cartera:
                return (
                    f"uv run invest-ll-portfolio cash deposit --amount {cantidad}"
                    f"   # {self.symbol} en el exchange que tu cartera no tiene registrado"
                )
            return (
                f"uv run invest-ll-portfolio cash withdraw --amount {cantidad}"
                f"   # tu cartera cree tener {cantidad} {self.symbol} de mas: revisa antes"
            )

        par = f"{self.symbol}/{MONEDA_DE_COTIZACION}"
        if self.falta_en_la_cartera:
            return (
                f"uv run invest-ll-portfolio add buy --symbol {par} --quantity {cantidad} "
                "--price <precio pagado> --fee <comision>"
                "   # con el precio y la comision reales de esa compra"
            )
        return (
            f"uv run invest-ll-portfolio add sell --symbol {par} --quantity {cantidad} "
            "--price <precio cobrado> --fee <comision>"
            f"   # tu cartera cree tener {cantidad} {self.symbol} que el exchange no ve: "
            "comprueba primero que de verdad se vendio"
        )


@dataclass(frozen=True, slots=True)
class Reconciliacion:
    """El resultado de comparar. Describe; no corrige."""

    diferencias: tuple[Diferencia, ...]
    """De mayor a menor descuadre."""
    otros_con_saldo: tuple[str, ...]
    """Activos con saldo en el exchange que nunca has tocado. No se comparan, pero se cuentan."""

    @property
    def cuadra(self) -> bool:
        return not self.diferencias

    def describe(self) -> str:
        if self.cuadra:
            texto = "Tu cartera cuadra con el exchange en todo lo que has tocado."
        else:
            nombres = [d.symbol for d in self.diferencias[:MAX_NOMBRES_EN_RESUMEN]]
            resto = len(self.diferencias) - len(nombres)
            lista = ", ".join(nombres) + (f" y {resto} mas" if resto else "")
            texto = (
                f"No cuadra: {len(self.diferencias)} diferencia(s) con el exchange ({lista}). "
                "No se ha ajustado nada: registra lo que falte con los comandos de abajo."
            )
        if self.otros_con_saldo:
            texto += (
                f" Hay {len(self.otros_con_saldo)} activo(s) con saldo que nunca has operado; "
                "no se comparan."
            )
        return texto


def reconciliar(
    *,
    exchange: Mapping[str, Decimal],
    cartera: Mapping[str, Decimal],
    relevantes: Iterable[str] | None = None,
) -> Reconciliacion:
    """Compara saldos por moneda.

    `relevantes` limita la comparación a lo que has tocado. Lo que tu cartera tiene se compara
    SIEMPRE, esté o no en esa lista: una posición que crees tener y el exchange no ve es peor señal
    que la contraria, y no puede quedar filtrada. Sin `relevantes` se compara todo.
    """
    if relevantes is None:
        comparados = set(exchange) | set(cartera)
    else:
        comparados = set(relevantes) | set(cartera)

    diferencias = [
        Diferencia(
            symbol=simbolo,
            en_el_exchange=exchange.get(simbolo, CERO),
            en_la_cartera=cartera.get(simbolo, CERO),
        )
        for simbolo in comparados
    ]
    diferencias = [d for d in diferencias if abs(d.falta_registrar) > POLVO]
    diferencias.sort(key=lambda d: (-abs(d.falta_registrar), d.symbol))

    otros = sorted(s for s, saldo in exchange.items() if s not in comparados and saldo > POLVO)
    return Reconciliacion(diferencias=tuple(diferencias), otros_con_saldo=tuple(otros))
