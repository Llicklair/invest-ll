"""Análisis de composición: ¿esta cartera diversifica de verdad?

Tener ocho activos no es diversificar. Si los ocho suben y bajan a la vez, en la práctica tienes
uno solo repetido ocho veces — y la caída del mal día te la comes entera igual.

**Sobre el look-ahead.** Este módulo se usa para decidir *hoy* qué comprar, y para eso mirar todo
el histórico disponible es legítimo: no se está simulando una decisión del pasado. Si algún día
una estrategia usa la correlación para decidir *dentro* de un backtest, tendrá que calcularla con
ventana móvil sobre lo visible hasta cada instante. Confundir las dos cosas es exactamente cómo se
cuela el look-ahead sin que nadie lo note.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.universe import Universe

# Por encima de esta correlación media, añadir activos deja de reducir el riesgo de forma
# apreciable. No es una frontera exacta: es el punto donde conviene mirar la cartera con recelo.
CORRELACION_ALTA = 0.7

# El criterio que de verdad decide, y la razón por la que la correlación media no basta.
#
# Seis sectores de bolsa dan una correlación media de 0,60 —por debajo del umbral anterior— y sin
# embargo equivalen a 1,5 activos independientes. Un aviso que no salta ahí no sirve para nada.
# Por debajo de dos activos efectivos, la cartera se comporta prácticamente como uno solo, tenga
# los que tenga.
MINIMO_ACTIVOS_EFECTIVOS = 2.0

MINIMO_PERIODOS = 30


@dataclass(frozen=True, slots=True)
class PairCorrelation:
    a: str
    b: str
    value: float

    def describe(self) -> str:
        return f"{self.a} / {self.b}: {self.value:+.2f}"


@dataclass(frozen=True, slots=True)
class PortfolioAnalysis:
    """Cómo de diversificada está una cartera."""

    symbols: tuple[str, ...]
    periods: int
    average_correlation: float
    pairs: tuple[PairCorrelation, ...]
    effective_assets: float

    @property
    def is_diversified(self) -> bool:
        """Diversifica si aporta al menos dos activos independientes y no van todos a una.

        Las dos condiciones hacen falta. La correlación media sola deja pasar carteras de seis
        sectores que equivalen a uno y medio; los activos efectivos solos darían por buena una
        cartera de dos activos casi idénticos, porque 1,2 de 2 suena a poca pérdida.
        """
        return (
            self.effective_assets >= MINIMO_ACTIVOS_EFECTIVOS
            and self.average_correlation < CORRELACION_ALTA
        )

    @property
    def most_correlated(self) -> PairCorrelation | None:
        return max(self.pairs, key=lambda p: p.value) if self.pairs else None

    @property
    def least_correlated(self) -> PairCorrelation | None:
        return min(self.pairs, key=lambda p: p.value) if self.pairs else None

    def render(self) -> str:
        lineas = [
            f"Diversificacion - {' / '.join(self.symbols)}",
            "=" * 52,
            f"  Activos             {len(self.symbols):>16}",
            f"  Activos efectivos   {self.effective_assets:>16.1f}",
            f"  Correlacion media   {self.average_correlation:>16.2f}",
        ]

        if not self.is_diversified:
            lineas += [
                "",
                f"  [!] Tus {len(self.symbols)} activos equivalen a {self.effective_assets:.1f}"
                " independientes.",
                f"      Con una correlacion media de {self.average_correlation:.2f} se mueven casi",
                "      a la vez: tener varios no te protege de una caida general, porque cuando",
                "      cae uno caen todos.",
            ]

        mas = self.most_correlated
        menos = self.least_correlated
        if mas is not None and menos is not None:
            lineas += [
                "",
                f"  Par mas parecido    {mas.describe()}",
                f"  Par mas distinto    {menos.describe()}",
            ]

        return "\n".join(lineas)

    def __str__(self) -> str:
        return self.render()


def analyze_portfolio(universe: Universe) -> PortfolioAnalysis:
    """Mide la correlación entre los activos del universo.

    La correlación se calcula sobre **rendimientos diarios**, no sobre precios. Dos activos que
    suben con pendientes distintas tienen precios muy correlacionados aunque se muevan por motivos
    independientes; lo que importa es si caen el mismo día.
    """
    if len(universe) < MINIMO_PERIODOS:
        raise ValueError(
            f"hacen falta al menos {MINIMO_PERIODOS} periodos para medir correlaciones, "
            f"hay {len(universe)}"
        )

    rendimientos: dict[str, np.ndarray] = {}
    for symbol in universe.symbols:
        cierres = np.array(
            [universe.bar(symbol, i).close for i in range(len(universe))], dtype=np.float64
        )
        rendimientos[symbol] = np.diff(cierres) / cierres[:-1]

    pares: list[PairCorrelation] = []
    for a, b in combinations(universe.symbols, 2):
        matriz = np.corrcoef(rendimientos[a], rendimientos[b])
        valor = float(matriz[0, 1])
        if np.isnan(valor):  # pragma: no cover - series constantes
            valor = 0.0
        pares.append(PairCorrelation(a=a, b=b, value=valor))

    media = float(np.mean([p.value for p in pares])) if pares else 0.0

    return PortfolioAnalysis(
        symbols=universe.symbols,
        periods=len(universe),
        average_correlation=media,
        pairs=tuple(pares),
        effective_assets=_effective_assets(len(universe.symbols), media),
    )


def _effective_assets(n: int, correlacion_media: float) -> float:
    """Cuántos activos independientes equivale a tener esta cartera.

    Con correlación 0 son `n` activos de verdad; con correlación 1 es uno solo repetido. La
    fórmula es la aproximación clásica de diversificación efectiva, y sirve para lo que importa:
    poner un número a la intuición de que ocho activos que se mueven igual no son ocho.
    """
    if n <= 1:
        return float(n)
    correlacion = max(0.0, min(1.0, correlacion_media))
    return n / (1 + (n - 1) * correlacion)
