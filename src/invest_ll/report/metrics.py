"""Cálculo de las métricas del veredicto (T031).

Las tres funciones son deliberadamente simples y están probadas por separado: son las cifras
sobre las que el operador decidirá si arriesga dinero.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal


def expectancy(results: Sequence[Decimal]) -> Decimal:
    """Resultado medio por operación.

    Es la cifra que el win rate no cuenta: mide cuánto se gana o se pierde de media, no cuántas
    veces se acierta. Una estrategia con win rate del 90% y expectancy negativa pierde dinero.
    """
    if not results:
        return Decimal(0)
    return sum(results, start=Decimal(0)) / len(results)


def max_drawdown(equity_curve: Sequence[Decimal]) -> Decimal:
    """Peor caída desde un máximo previo. Nunca positiva.

    Se devuelve en negativo para que no pueda confundirse con una ganancia al leerla de un
    vistazo.
    """
    if not equity_curve:
        return Decimal(0)

    peak = equity_curve[0]
    worst = Decimal(0)
    for value in equity_curve:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def win_rate(results: Sequence[Decimal]) -> float:
    """Proporción de operaciones con resultado positivo.

    **No es un criterio de éxito** (FR-012). Se calcula porque el operador lo pide y porque
    ocultarlo sería paternalista, pero el informe nunca lo presenta solo. Una operación plana no
    cuenta como ganadora.
    """
    if not results:
        return 0.0
    ganadoras = sum(1 for r in results if r > 0)
    return ganadoras / len(results)
