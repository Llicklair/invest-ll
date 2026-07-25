"""Aportaciones periódicas sobre una cartera diversificada.

Comprar una cantidad fija cada mes, repartida entre varios activos, y no tocar nada. Sin predecir,
sin elegir momento, sin vender.

**Qué mide y qué no.** Las aportaciones periódicas no buscan batir a nadie: buscan quitar de la
ecuación el momento de entrada. Invertir todo de golpe suele rendir más —el mercado sube más
tiempo del que baja— pero te juegas el resultado a la fecha en que entraste. Aportar poco a poco
renuncia a parte del retorno a cambio de que esa fecha deje de importar.

**La trampa que este módulo evita.** Medir "meses en verde" sobre el saldo de la cartera daría
casi siempre verde, porque cada mes entra dinero nuevo aunque el mercado caiga. Aquí la curva que
se analiza es la **ganancia acumulada** —valor menos aportado—, que es lo único que refleja si la
inversión está funcionando.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.execution import MOTOR, OrderSide, apply_slippage
from invest_ll.report.consistency import Consistency, monthly_consistency
from invest_ll.report.metrics import max_drawdown

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.universe import Universe
    from invest_ll.engine.config import FrictionConfig

LOTE_MINIMO = Decimal("0.00000001")


@dataclass(frozen=True, slots=True)
class DCAReport:
    """Resultado de un plan de aportaciones periódicas."""

    symbols: tuple[str, ...]
    contributions: int
    total_contributed: Decimal
    final_value: Decimal
    total_costs: Decimal
    max_drawdown: Decimal
    consistency: Consistency
    lump_sum_value: Decimal

    @property
    def net_result(self) -> Decimal:
        return self.final_value - self.total_contributed

    @property
    def return_on_contributions(self) -> float:
        if self.total_contributed == 0:
            return 0.0
        return float(self.net_result / self.total_contributed)

    @property
    def beats_lump_sum(self) -> bool:
        return self.final_value > self.lump_sum_value

    def render(self) -> str:
        lineas = [
            f"Aportaciones periodicas - {' / '.join(self.symbols)}",
            "=" * 52,
            f"  Aportaciones        {self.contributions:>16}",
            f"  Total aportado      {self.total_contributed:>16.2f}",
            f"  Valor final         {self.final_value:>16.2f}",
            f"  Ganancia            {self.net_result:>16.2f}"
            f"  ({self.return_on_contributions:+.1%})",
            f"  Costes totales      {self.total_costs:>16.2f}",
            f"  Drawdown maximo     {self.max_drawdown:>16.2f}",
            "",
            "  Frente a invertirlo todo de golpe al principio",
            f"    aportando poco a poco {self.final_value:>16.2f}",
            f"    todo de golpe         {self.lump_sum_value:>16.2f}",
        ]

        if self.beats_lump_sum:
            lineas.append("    -> aportar poco a poco salio mejor en este periodo")
        else:
            lineas += [
                "    -> invertir de golpe habria rendido mas, como suele pasar.",
                "       Aportar poco a poco no busca ganar mas: busca que la fecha",
                "       de entrada deje de decidir el resultado.",
            ]

        c = self.consistency
        if c.periods:
            lineas += [
                "",
                "  Regularidad de la GANANCIA (no del saldo)",
                f"    meses en verde    {c.positive_periods}/{c.periods}  ({c.positive_ratio:.0%})",
                f"    peor mes          {c.worst_period:>12.2f}",
                f"    racha en rojo     {c.longest_losing_streak} mes(es) seguidos",
            ]

        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def run_dca(
    universe: Universe,
    *,
    contribution: Decimal,
    friction: FrictionConfig,
    every_periods: int = 21,
) -> DCAReport:
    """Aporta `contribution` cada `every_periods`, repartido a partes iguales.

    21 periodos es aproximadamente un mes de sesiones bursátiles. No se vende nunca: cada
    aportación compra y ya está.
    """
    if contribution <= 0:
        raise ValueError(f"la aportación debe ser positiva, recibida {contribution}")
    if every_periods < 1:
        raise ValueError("el intervalo entre aportaciones debe ser de al menos 1 periodo")
    if len(universe) < 2:
        raise ValueError("hacen falta al menos dos periodos para aportar y valorar")

    unidades: dict[str, Decimal] = dict.fromkeys(universe.symbols, Decimal(0))
    aportado = Decimal(0)
    costes = Decimal(0)
    aportaciones = 0

    ganancia: list[Decimal] = []
    marcas: list[datetime] = []

    for i in range(len(universe)):
        # Aportar. Se compra en la apertura del periodo siguiente, igual que en el resto del
        # motor: la decisión de aportar se toma con el periodo actual ya cerrado.
        if i % every_periods == 0 and i + 1 < len(universe):
            aportado += contribution
            aportaciones += 1
            por_activo = contribution / len(universe.symbols)

            for symbol in universe.symbols:
                referencia = Decimal(str(universe.bar(symbol, i + 1).open))
                compra = apply_slippage(referencia, OrderSide.BUY, friction.slippage_rate)
                unitario = MOTOR.multiply(compra, 1 + friction.commission_rate)
                cantidad = MOTOR.divide(por_activo, unitario).quantize(
                    LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
                )
                if cantidad <= 0:
                    continue
                unidades[symbol] += cantidad
                costes += MOTOR.multiply(MOTOR.multiply(compra, cantidad), friction.commission_rate)
                costes += MOTOR.multiply(compra - referencia, cantidad)

        valor = sum(
            (
                MOTOR.multiply(cantidad, Decimal(str(universe.bar(symbol, i).close)))
                for symbol, cantidad in unidades.items()
            ),
            start=Decimal(0),
        )
        # La curva analizada es la GANANCIA, no el saldo: el saldo sube cada mes por la aportación
        # y daría una regularidad falsa.
        ganancia.append(valor - aportado)
        marcas.append(universe.timestamps[i])

    valor_final = sum(
        (
            MOTOR.multiply(cantidad, Decimal(str(universe.bar(symbol, len(universe) - 1).close)))
            for symbol, cantidad in unidades.items()
        ),
        start=Decimal(0),
    )

    return DCAReport(
        symbols=universe.symbols,
        contributions=aportaciones,
        total_contributed=aportado,
        final_value=valor_final,
        total_costs=costes,
        max_drawdown=max_drawdown(ganancia),
        consistency=monthly_consistency(ganancia, marcas),
        lump_sum_value=_lump_sum(universe, capital=aportado, friction=friction),
    )


def _lump_sum(universe: Universe, *, capital: Decimal, friction: FrictionConfig) -> Decimal:
    """Valor final de invertir todo el capital de golpe al principio.

    Es el benchmark honesto para las aportaciones periódicas: mismo dinero, misma cartera, una
    sola entrada. Comparar contra otra cosa escondería el coste real de repartir la entrada.
    """
    if capital <= 0 or len(universe) < 2:
        return Decimal(0)

    por_activo = capital / len(universe.symbols)
    total = Decimal(0)

    for symbol in universe.symbols:
        referencia = Decimal(str(universe.bar(symbol, 1).open))
        compra = apply_slippage(referencia, OrderSide.BUY, friction.slippage_rate)
        unitario = MOTOR.multiply(compra, 1 + friction.commission_rate)
        cantidad = MOTOR.divide(por_activo, unitario).quantize(
            LOTE_MINIMO, rounding=ROUND_DOWN, context=MOTOR
        )
        final = Decimal(str(universe.bar(symbol, len(universe) - 1).close))
        total += MOTOR.multiply(cantidad, final)

    return total
