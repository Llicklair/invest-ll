"""Los indicadores de las estrategias a medida, calculados sobre velas CERRADAS. Puro.

Cada indicador mira una ventana FIJA de velas (`Indicador.ventana`): la media exponencial y el RSI
arrancan de la media simple al principio de su ventana en vez de arrastrar toda la historia que
haya. Así su valor depende solo de las últimas velas, y el bot en vivo (que pide a la fuente las
velas justas) y la prueba sobre el pasado (que tiene años) calculan exactamente lo mismo.

Se calcula en coma flotante: son umbrales de decisión, no dinero. El dinero (cantidades, importes,
comisiones) sigue en Decimal en la cuenta del bot.
"""

from __future__ import annotations

import statistics
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.estrategias_custom.formato import Fuente, Indicador
    from invest_ll.vivo.fuente import Vela


def dato(vela: Vela, fuente: Fuente) -> float:
    if fuente == "cierre":
        return float(vela.cierre)
    if fuente == "apertura":
        return float(vela.apertura)
    if fuente == "maximo":
        return float(vela.maximo)
    if fuente == "minimo":
        return float(vela.minimo)
    return float(vela.volumen)


def _ema(valores: Sequence[float], periodo: int) -> float:
    alfa = 2 / (periodo + 1)
    media = sum(valores[:periodo]) / periodo
    for v in valores[periodo:]:
        media = alfa * v + (1 - alfa) * media
    return media


def _rsi(valores: Sequence[float], periodo: int) -> float:
    """El RSI de Wilder: medias suavizadas de subidas y bajadas, de 0 a 100."""
    cambios = [b - a for a, b in pairwise(valores)]
    sube = sum(max(c, 0.0) for c in cambios[:periodo]) / periodo
    baja = sum(max(-c, 0.0) for c in cambios[:periodo]) / periodo
    for c in cambios[periodo:]:
        sube = (sube * (periodo - 1) + max(c, 0.0)) / periodo
        baja = (baja * (periodo - 1) + max(-c, 0.0)) / periodo
    if baja == 0:
        return 100.0 if sube > 0 else 50.0
    return 100 - 100 / (1 + sube / baja)


def _cambios(valores: Sequence[float]) -> list[float] | None:
    if any(v == 0 for v in valores[:-1]):
        return None
    return [b / a - 1 for a, b in pairwise(valores)]


def _atr(velas: Sequence[Vela]) -> float:
    rangos: list[float] = []
    for antes, vela in pairwise(velas):
        alto, bajo, cierre = float(vela.maximo), float(vela.minimo), float(antes.cierre)
        rangos.append(max(alto - bajo, abs(alto - cierre), abs(bajo - cierre)))
    return sum(rangos) / len(rangos)


def calcular(ind: Indicador, velas: Sequence[Vela], hace: int = 0) -> float | None:
    """El valor del indicador con las velas cerradas `velas` (de la más antigua a la más
    reciente), tal como estaba `hace` velas (además de su propio `atras`). None si no hay
    bastantes velas o no se puede calcular (un precio cero)."""
    fin = len(velas) - ind.atras - hace
    ventana = ind.ventana
    if fin < ventana or ventana <= 0:
        return None
    tramo = velas[fin - ventana : fin]
    if ind.tipo == "atr":
        return _atr(tramo)
    valores = [dato(v, ind.de) for v in tramo]
    n = ind.periodo
    if ind.tipo in ("sma", "volumen_medio"):
        return sum(valores) / n
    if ind.tipo == "ema":
        return _ema(valores, n)
    if ind.tipo == "rsi":
        return _rsi(valores, n)
    if ind.tipo == "maximo":
        return max(valores)
    if ind.tipo == "minimo":
        return min(valores)
    cambios = _cambios(valores)
    if cambios is None:
        return None
    if ind.tipo == "retorno":
        return valores[-1] / valores[0] - 1
    return statistics.pstdev(cambios)  # volatilidad


def volatilidad(velas: Sequence[Vela], periodo: int) -> float | None:
    """La desviación típica del cambio de cada vela en las últimas `periodo` (para repartir)."""
    if len(velas) < periodo + 1:
        return None
    cambios = _cambios([float(v.cierre) for v in velas[-periodo - 1 :]])
    return statistics.pstdev(cambios) if cambios else None
