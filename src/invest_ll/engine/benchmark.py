"""Comprar y mantener: el listón que toda estrategia tiene que superar.

Una estrategia que no bate a no hacer nada no justifica su existencia. Ha corrido riesgo, ha
pagado comisiones y ha exigido atención, todo para quedarse por debajo de lo que consigue quien
compra y se olvida. El win rate puede ser precioso y dar igual.

Se calcula con la **misma fricción** que la estrategia — comprar y mantener también paga su
comisión de entrada y de salida — porque comparar contra un benchmark sin costes sería hacer
trampa a favor de la estrategia.

Y se reporta también su drawdown. Sin eso la comparación sería injusta en el otro sentido: ganar
algo menos sufriendo mucho menos por el camino es un resultado legítimo, y muchas veces el único
que se aguanta sin abandonar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.execution import MOTOR, OrderSide, apply_slippage
from invest_ll.report.metrics import max_drawdown

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.series import PriceSeries
    from invest_ll.engine.config import FrictionConfig

LOTE_MINIMO = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class BuyAndHold:
    """Lo que habría conseguido comprar al principio y no volver a mirar."""

    net_result: Decimal
    costs: Decimal
    max_drawdown: Decimal
    quantity: Decimal

    @property
    def did_nothing(self) -> bool:
        """No hubo forma de entrar: serie demasiado corta o capital insuficiente."""
        return self.quantity == 0


def buy_and_hold(series: PriceSeries, *, capital: Decimal, friction: FrictionConfig) -> BuyAndHold:
    """Compra en la apertura del segundo periodo y vende al último cierre.

    Entra en el segundo periodo, no en el primero, por el mismo motivo que el motor: la decisión
    se toma con el primer periodo ya cerrado y se ejecuta a la apertura siguiente. Comparar contra
    un benchmark que entra un periodo antes le daría una ventaja que la estrategia no tiene.
    """
    if len(series) < 2 or capital <= 0:
        return BuyAndHold(
            net_result=Decimal(0),
            costs=Decimal(0),
            max_drawdown=Decimal(0),
            quantity=Decimal(0),
        )

    entrada = Decimal(str(series.bars[1].open))
    salida = Decimal(str(series.bars[-1].close))

    precio_compra = apply_slippage(entrada, OrderSide.BUY, friction.slippage_rate)
    precio_venta = apply_slippage(salida, OrderSide.SELL, friction.slippage_rate)

    coste_unitario = MOTOR.multiply(precio_compra, 1 + friction.commission_rate)
    quantity = MOTOR.divide(capital, coste_unitario).quantize(
        LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
    )
    if quantity <= 0:
        return BuyAndHold(
            net_result=Decimal(0),
            costs=Decimal(0),
            max_drawdown=Decimal(0),
            quantity=Decimal(0),
        )

    comision_compra = MOTOR.multiply(
        MOTOR.multiply(precio_compra, quantity), friction.commission_rate
    )
    comision_venta = MOTOR.multiply(
        MOTOR.multiply(precio_venta, quantity), friction.commission_rate
    )
    slippage = MOTOR.multiply(abs(precio_compra - entrada) + abs(salida - precio_venta), quantity)

    bruto = MOTOR.multiply(salida - entrada, quantity)
    costes = comision_compra + comision_venta + slippage

    # La curva de patrimonio del benchmark: capital invertido valorado a cada cierre.
    equity = [MOTOR.multiply(Decimal(str(bar.close)), quantity) for bar in series.bars[1:]]

    return BuyAndHold(
        net_result=bruto - costes,
        costs=costes,
        max_drawdown=max_drawdown(equity),
        quantity=quantity,
    )
