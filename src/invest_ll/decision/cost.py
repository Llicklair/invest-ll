"""Cuánto va a costar un backtest, antes de lanzarlo (FR-041).

Existe porque el operador eligió que el LLM decida también el *cuándo*. A una decisión por vela,
un backtest de 21 años son más de 5.000 llamadas: cientos de euros y varias horas. Eso no puede
salir de un comando lanzado por descuido.

Las cifras son estimaciones, no facturas. Se redondean hacia arriba a propósito: equivocarse
diciendo que costará más de lo que cuesta es inofensivo; al revés, no.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from invest_ll.decision.anthropic_provider import PRECIO_ENTRADA, PRECIO_SALIDA

# Medido sobre contextos reales del proyecto: unos 4.000 tokens de entrada por decision
# (instrucciones + serie normalizada de varios activos) y ~800 de salida.
TOKENS_ENTRADA_POR_DECISION = 4000
TOKENS_SALIDA_POR_DECISION = 800

# Por encima de esto se pide confirmación. 300 decisiones ≈ un backtest mensual de 25 años,
# que es el caso normal; a partir de ahí conviene mirar antes de pagar.
UMBRAL_CONFIRMACION = 300

UN_MILLON = Decimal(1_000_000)
CENTIMO = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class CostEstimate:
    """Lo que costará, separando lo que ya está pagado."""

    total_decisions: int
    cached_decisions: int
    threshold: int = UMBRAL_CONFIRMACION

    @property
    def new_decisions(self) -> int:
        """Las que hay que preguntar de verdad. Es lo único que se paga."""
        return max(0, self.total_decisions - self.cached_decisions)

    @property
    def estimated_cost(self) -> Decimal:
        """En dólares, redondeado hacia arriba al céntimo."""
        entrada = (
            Decimal(self.new_decisions * TOKENS_ENTRADA_POR_DECISION)
            / UN_MILLON
            * Decimal(str(PRECIO_ENTRADA))
        )
        salida = (
            Decimal(self.new_decisions * TOKENS_SALIDA_POR_DECISION)
            / UN_MILLON
            * Decimal(str(PRECIO_SALIDA))
        )
        return (entrada + salida).quantize(CENTIMO, rounding=ROUND_CEILING)

    @property
    def needs_confirmation(self) -> bool:
        return self.new_decisions > self.threshold

    def render(self) -> str:
        if self.new_decisions == 0:
            return (
                f"Las {self.total_decisions} decisiones ya estan cacheadas. "
                "Coste: 0. El resultado sera identico al anterior."
            )

        lineas = [
            f"Este backtest necesita {self.new_decisions} decisiones nuevas "
            f"de {self.total_decisions} (~${self.estimated_cost}).",
        ]
        if self.cached_decisions:
            lineas.append(f"  {self.cached_decisions} ya estan cacheadas y no se pagan.")
        if self.needs_confirmation:
            lineas.append(
                f"  [!] Supera el umbral de {self.threshold}. "
                "Con periodicidad mensual serian bastantes menos."
            )
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def estimate_cost(
    total_decisions: int,
    cached_decisions: int = 0,
    *,
    threshold: int = UMBRAL_CONFIRMACION,
) -> CostEstimate:
    """Estima el coste de un backtest.

    `cached_decisions` sale de contar cuántas claves ya están en el almacén — por eso conviene
    calcularlo antes de preguntar nada.
    """
    if total_decisions < 0:
        raise ValueError("el numero de decisiones no puede ser negativo")
    if cached_decisions < 0:
        raise ValueError("las decisiones cacheadas no pueden ser negativas")
    return CostEstimate(
        total_decisions=total_decisions,
        cached_decisions=min(cached_decisions, total_decisions),
        threshold=threshold,
    )
