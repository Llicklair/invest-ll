"""Propuesta de cartera a partir de lo único que el operador sabe: cuánto y cada cuánto.

No pide elegir estrategia ni parámetros **a propósito**. Ese es justo el conocimiento que el
operador ha declarado no tener, y un sistema que se lo exige no le sirve de nada.

Lo que propone no es una apuesta: es lo único que la evidencia respalda —aportaciones periódicas
sobre una cartera diversificada— acompañado de la simulación de qué habría pasado y de la
comparación contra no hacer nada. Ver `docs/research-estrategias.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from invest_ll.engine.dca import run_dca
from invest_ll.report.portfolio import analyze_portfolio

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.universe import Universe
    from invest_ll.engine.config import FrictionConfig
    from invest_ll.engine.dca import DcaReport
    from invest_ll.report.portfolio import PortfolioAnalysis

CENTIMO = Decimal("0.01")

# Periodos entre aportaciones, en velas diarias.
FRECUENCIAS = {
    "monthly": 21,
    "quarterly": 63,
    "weekly": 5,
}

# Por qué está cada tipo de activo, en lenguaje que no exige saber de inversión (FR-004).
EXPLICACIONES = {
    "GLD": "Oro. Suele moverse distinto que las acciones, asi que amortigua cuando estas caen.",
    "TLT": "Bonos del Estado a largo plazo. Historicamente suben cuando las acciones caen.",
    "SPY": "Las 500 empresas mas grandes de EE.UU. Es la referencia contra la que todo se mide.",
    "QQQ": "Las tecnologicas grandes. Sube mas y cae mas.",
    "XLK": "Sector tecnologico.",
    "XLF": "Bancos y aseguradoras.",
    "XLE": "Petroleras y energia.",
    "XLV": "Farmaceuticas y sanidad.",
    "XLP": "Consumo basico: comida, limpieza. Lo que se compra pase lo que pase.",
    "AAPL": "Una sola empresa. Concentrar en una companhia es mas arriesgado que en un sector.",
    "BTC/USDT": "Bitcoin. Sube y baja mucho mas que todo lo demas: si entra, que sea poco.",
}

EXPLICACION_GENERICA = "Sin descripcion disponible para este activo."


@dataclass(frozen=True, slots=True)
class Holding:
    """Un activo dentro de la propuesta."""

    symbol: str
    weight: Decimal
    amount_per_contribution: Decimal
    explanation: str


@dataclass(frozen=True, slots=True)
class Proposal:
    """Qué comprar, por qué, y qué habría pasado si lo hubieras hecho."""

    holdings: tuple[Holding, ...]
    contribution: Decimal
    every_periods: int
    simulation: DcaReport
    diversification: PortfolioAnalysis

    @property
    def total_per_contribution(self) -> Decimal:
        return sum((h.amount_per_contribution for h in self.holdings), start=Decimal(0))

    def render(self) -> str:
        lineas = [
            "Propuesta de cartera",
            "=" * 72,
            f"Aportacion: {self.contribution} cada {self.every_periods} periodos",
            "",
        ]
        for h in self.holdings:
            lineas.append(f"  {h.symbol:<10}{h.amount_per_contribution:>10,.2f}  ({h.weight:.0%})")
            lineas.append(f"      {h.explanation}")
        lineas.append("")

        # Lo primero que se lee tras la cartera es si diversifica de verdad, no cuanto gana.
        d = self.diversification
        lineas.append(
            f"Diversificacion: {len(d.symbols)} activos equivalen a "
            f"{d.effective_assets:.1f} independientes "
            f"(correlacion media {d.average_correlation:.2f})"
        )
        if not d.is_diversified:
            lineas.append(
                "  [!] Se mueven casi a la vez: tener varios no te protege de una caida general."
            )
        lineas.append("")
        lineas.append(self.simulation.render())
        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def propose_portfolio(
    universe: Universe,
    *,
    amount: Decimal,
    frequency: str = "monthly",
    friction: FrictionConfig,
) -> Proposal:
    """Propone una cartera y simula qué habría pasado con ella.

    El reparto es a partes iguales. No es una simplificación perezosa: repartir por partes
    iguales no requiere estimar rentabilidades futuras, y estimarlas es justo donde se cuela el
    optimismo. Cualquier reparto "optimizado" sobre datos pasados es una forma de mirar la
    respuesta antes de responder.
    """
    if amount <= 0:
        raise ValueError(f"la aportacion debe ser positiva, recibido {amount}")
    if frequency not in FRECUENCIAS:
        raise ValueError(f"frecuencia desconocida {frequency!r}; opciones: {sorted(FRECUENCIAS)}")

    simbolos = tuple(universe.symbols)
    if not simbolos:
        raise ValueError("no hay activos que proponer")

    cada = FRECUENCIAS[frequency]
    peso = Decimal(1) / Decimal(len(simbolos))
    por_activo = (amount * peso).quantize(CENTIMO, rounding=ROUND_DOWN)

    holdings = tuple(
        Holding(
            symbol=s,
            weight=peso,
            amount_per_contribution=por_activo,
            explanation=EXPLICACIONES.get(s, EXPLICACION_GENERICA),
        )
        for s in simbolos
    )

    return Proposal(
        holdings=holdings,
        contribution=amount,
        every_periods=cada,
        simulation=run_dca(universe, contribution=amount, friction=friction, every_periods=cada),
        diversification=analyze_portfolio(universe),
    )
