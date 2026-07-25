"""Nota de 1 a 10 para decidir si un activo es candidato a inversión.

La idea del operador: antes de invertir, investigar cada activo y puntuarlo. Solo los que pasan
del 7 entran en la rotación.

**Todo se calcula con datos de precio.** No con fundamentales, y no por pereza: el PER o la deuda
que se ven hoy no son los que se conocían en 2018. Usarlos para decidir en el pasado es
look-ahead, y los datos históricos con fecha de publicación real son de pago. Con precios la
garantía del Principio II se mantiene intacta.

**Los pesos y los umbrales están fijados aquí, no ajustados a resultados.** Cada componente que se
añade es un grado de libertad más para amoldar el pasado, y una nota con cinco pesos afinados
sobre el histórico es una forma elegante de sobreajustar. Si algún día se tocan, hay que
revalidar fuera de muestra.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.engine.universe_view import UniverseView

NOTA_MINIMA = 1.0
NOTA_MAXIMA = 10.0
UMBRAL_CANDIDATO = 7.0

# Periodos de las ventanas. Fijos a propósito: son valores convencionales (un trimestre, un mes),
# no números encontrados probando cuál daba mejor resultado.
VENTANA_LARGA = 120
VENTANA_CORTA = 20


@dataclass(frozen=True, slots=True)
class AssetScore:
    """Nota de un activo y el desglose de cómo se llegó a ella.

    El desglose no es decorativo: una nota de 7 sin explicación es un número que hay que creerse.
    Con el desglose se puede discutir.
    """

    symbol: str
    score: float
    trend: float
    momentum: float
    consistency: float
    risk: float

    @property
    def is_candidate(self) -> bool:
        return self.score >= UMBRAL_CANDIDATO

    def describe(self) -> str:
        return (
            f"{self.symbol:<10} nota {self.score:>4.1f}  "
            f"(tendencia {self.trend:.1f} - impulso {self.momentum:.1f} - "
            f"regularidad {self.consistency:.1f} · riesgo {self.risk:.1f})"
        )


def _escalar(valor: float, malo: float, bueno: float) -> float:
    """Lleva un valor a la escala 1-10 de forma lineal y acotada."""
    if bueno == malo:
        return NOTA_MINIMA
    proporcion = (valor - malo) / (bueno - malo)
    acotada = max(0.0, min(1.0, proporcion))
    return NOTA_MINIMA + acotada * (NOTA_MAXIMA - NOTA_MINIMA)


def score_asset(view: UniverseView, symbol: str) -> AssetScore | None:
    """Puntúa un activo con lo que se sabía en el instante de la vista.

    Devuelve `None` si no hay histórico suficiente. No se puntúa con menos datos de los pedidos:
    daría notas altas por azar a los activos recién incorporados.
    """
    if len(view) < VENTANA_LARGA + 1:
        return None

    cierres = view.closes(symbol, VENTANA_LARGA)
    if len(cierres) < VENTANA_LARGA or cierres[0] <= 0:
        return None

    actual = cierres[-1]
    media_larga = sum(cierres) / len(cierres)
    recientes = cierres[-VENTANA_CORTA:]

    # Tendencia: cuánto está el precio por encima de su media larga.
    trend = _escalar(actual / media_larga - 1.0, malo=-0.15, bueno=0.25)

    # Impulso: rendimiento del último trimestre.
    momentum = _escalar(actual / cierres[0] - 1.0, malo=-0.20, bueno=0.40)

    # Regularidad: proporción de periodos recientes que cerraron al alza.
    subidas = sum(1 for antes, despues in pairwise(recientes) if despues > antes)
    consistency = _escalar(subidas / max(len(recientes) - 1, 1), malo=0.35, bueno=0.65)

    # Riesgo: caída máxima del trimestre. Es el único componente donde más es peor, y por eso se
    # invierte la escala — un activo que subió mucho tras desplomarse no merece nota alta.
    pico = cierres[0]
    peor = 0.0
    for precio in cierres:
        pico = max(pico, precio)
        peor = min(peor, precio / pico - 1.0)
    risk = _escalar(peor, malo=-0.45, bueno=-0.08)

    # Pesos iguales salvo el riesgo, que pesa menos porque en activos muy volátiles hundiría a
    # todos por igual y dejaría de discriminar. Fijados de antemano, no ajustados a resultados.
    score = trend * 0.3 + momentum * 0.3 + consistency * 0.2 + risk * 0.2

    return AssetScore(
        symbol=symbol,
        score=round(score, 1),
        trend=round(trend, 1),
        momentum=round(momentum, 1),
        consistency=round(consistency, 1),
        risk=round(risk, 1),
    )


def score_all(view: UniverseView) -> list[AssetScore]:
    """Puntúa todos los activos del universo, de mejor a peor."""
    notas = [score_asset(view, symbol) for symbol in view.symbols]
    return sorted((n for n in notas if n is not None), key=lambda n: n.score, reverse=True)


class ScoredRotation:
    """Rota entre los activos que superan el umbral, quedándose con el de mejor nota.

    Si ninguno lo supera, se queda **fuera del mercado**. Es la diferencia con el momentum puro:
    aquel siempre elige al mejor de la clase aunque toda la clase esté suspendiendo.
    """

    __slots__ = ("_threshold",)

    def __init__(self, threshold: float = UMBRAL_CANDIDATO) -> None:
        if not NOTA_MINIMA <= threshold <= NOTA_MAXIMA:
            raise ValueError(
                f"el umbral debe estar entre {NOTA_MINIMA} y {NOTA_MAXIMA}, recibido {threshold}"
            )
        self._threshold = threshold

    def choose(self, view: UniverseView) -> str | None:
        for nota in score_all(view):
            if nota.score >= self._threshold:
                return nota.symbol
        return None

    def __repr__(self) -> str:
        return f"ScoredRotation(threshold={self._threshold})"
