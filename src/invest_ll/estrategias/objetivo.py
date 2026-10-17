"""El reparto que quiere cada estrategia tras el último cierre: lo que "Qué toca hoy" persigue.

- Cripto: `quant.paper.current_targets`, la misma función que escribe los registros de la prueba
  hacia delante (`paper/*.jsonl`). Así la orden que propone el panel para "Bitcoin con freno" es la
  misma decisión que queda registrada para medirla.
- Bolsa: el equivalente sobre las sesiones del panel de ETF, con el calendario de decisiones de la
  ejecución del catálogo (cada `rebalanceo` sesiones desde el 1-ene-2008, en tramos escalonados).
  Sin universo de liquidez, como `run_etf_study`.

En los dos casos se usa una instancia NUEVA de la estrategia (`Motor.fabrica`): comprar y mantener
recuerda si ya compró y, compartida, respondería "nada" a partir de la segunda pregunta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Final

import numpy as np

from invest_ll.estrategias import datos
from invest_ll.estrategias.catalogo import ficha as ficha_de
from invest_ll.nombres import base
from invest_ll.quant.paper import current_targets
from invest_ll.quant.study import FLAGSHIP_UNIVERSE
from invest_ll.quant.view import MarketView

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.estrategias.catalogo import Ficha
    from invest_ll.estrategias.datos import Huella
    from invest_ll.quant.panel import FloatArray, Panel

PESO_MINIMO: Final = 1e-6


@dataclass(frozen=True, slots=True)
class Objetivo:
    """Pesos por activo (`BTC`, `SPY`: sin la moneda de cotización) tras el cierre de `fecha`."""

    fecha: date
    pesos: dict[str, float]


@lru_cache(maxsize=16)
def _de_hoy(clave: str, huella: Huella) -> Objetivo | None:
    del huella  # solo indexa la cache: cambia si el fichero de datos se reescribe
    encontrada = ficha_de(clave)
    if encontrada is None:
        return None
    p = datos.panel(encontrada.mercado)
    return None if p is None else pesos_de_hoy(encontrada, p)


def de_hoy(ficha: Ficha) -> Objetivo | None:
    """El objetivo de hoy con los datos descargados (en memoria por la huella del fichero).

    `None` si faltan los datos de su mercado.
    """
    huella = datos.huella(ficha.mercado)
    return None if huella is None else _de_hoy(ficha.clave, huella)


def pesos_de_hoy(ficha: Ficha, panel: Panel) -> Objetivo:
    """El reparto combinado de los tramos de la estrategia tras el último cierre del panel."""
    motor = ficha.motor
    if ficha.mercado == "cripto":
        pesos = current_targets(
            panel,
            motor.fabrica(),
            motor.universo or FLAGSHIP_UNIVERSE,
            rebalance_every=motor.rebalanceo,
            tranches=motor.tramos,
        )
    else:
        pesos = _tramos_de_bolsa(ficha, panel)
    por_activo: dict[str, float] = {}
    for i, w in enumerate(pesos):
        if float(w) > PESO_MINIMO:
            activo = base(panel.symbols[i])
            por_activo[activo] = por_activo.get(activo, 0.0) + float(w)
    return Objetivo(fecha=panel.date_at(len(panel) - 1), pesos=por_activo)


def _tramos_de_bolsa(ficha: Ficha, panel: Panel) -> FloatArray:
    """Como decide `engine.run` en la ejecución del catálogo: cada tramo, su última decisión."""
    motor = ficha.motor
    t = len(panel) - 1
    inicio = min(panel.index_of(motor.inicio), t)
    desde_inicio = t - inicio
    separacion = max(1, motor.rebalanceo // motor.tramos)
    total = np.zeros(len(panel.symbols))
    for j in range(motor.tramos):
        propio = desde_inicio - j * separacion
        if propio < 0:
            continue  # este tramo aún no había decidido: su parte sigue en liquidez
        decision = t - (propio % motor.rebalanceo)
        w = motor.fabrica().weights(MarketView(panel, decision, None))
        if w is not None:
            total += np.clip(np.nan_to_num(w, nan=0.0), 0.0, None)
    return total / motor.tramos
