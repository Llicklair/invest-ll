"""Cada estrategia del catálogo ejecutada sobre los datos descargados, con los costes del estudio.

Es la única fuente de las cifras que ve el usuario: lo que hizo con 10.000 desde el principio de
los datos (`Cifras`) y la curva diaria sobre la que se simulan sus aportaciones (`Recorrido`). Se
ejecuta con `invest_ll.quant.engine.run` y la misma configuración que el estudio del 2026-10-16
(`catalogo.Motor`), así que las cifras deben parecerse a las de docs/quant-research.md salvo por
los datos que se hayan descargado después.

Ejecutar el catálogo entero cuesta unos segundos (la cesta prerregistrada, con siete tramos y un
universo de cientos de monedas, es lo más caro), así que se guarda en memoria por la huella del
fichero de datos y se calcula una sola vez aunque lleguen varias peticiones a la vez. Solo se
guarda lo que el panel usa: la curva y el tiempo invertido de cada día, no la matriz de pesos.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final

import numpy as np

from invest_ll.estrategias import datos
from invest_ll.estrategias.catalogo import CALENTAMIENTO_CRIPTO, del_mercado
from invest_ll.quant.engine import RunConfig, run
from invest_ll.quant.metrics import drawdown, longest_drawdown
from invest_ll.quant.universe import PointInTimeUniverse

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.estrategias.catalogo import Ficha, Mercado
    from invest_ll.quant.panel import FloatArray, IntArray, Panel

CAPITAL: Final = 10_000.0
FALLOS_DE_DATOS = (KeyError, ValueError, IndexError, ZeroDivisionError)
"""Lo que lanza el motor cuando el panel no trae lo que la estrategia necesita (p. ej. SPY)."""


@dataclass(frozen=True, slots=True)
class Recorrido:
    """Una ejecución, reducida a lo que se enseña. `valor[0]` es el capital inicial."""

    clave: str
    dias: IntArray
    valor: FloatArray
    invertido: FloatArray
    operaciones: int
    periodos_al_anio: int

    @property
    def desde(self) -> date:
        return _fecha(int(self.dias[0]))

    @property
    def hasta(self) -> date:
        return _fecha(int(self.dias[-1]))


@dataclass(frozen=True, slots=True)
class Cifras:
    """Lo que hizo con 10.000 desde el principio de los datos. Ver `schemas_v2.Historico`."""

    desde: date
    hasta: date
    valor_final: float
    crecimiento_anual: float
    peor_caida: float
    peor_caida_fecha: date
    peor_racha_anios: float
    tiempo_invertido: float
    operaciones_al_anio: float


@dataclass(frozen=True, slots=True)
class Ejecucion:
    """El resultado de una estrategia: su recorrido, o por qué no se pudo calcular."""

    recorrido: Recorrido | None
    motivo: str | None


def _fecha(dia: int) -> date:
    return datetime.fromtimestamp(dia * 86_400, UTC).date()


def ejecutar(ficha: Ficha, panel: Panel) -> Recorrido:
    """Ejecuta la ficha sobre el panel completo con la configuración del estudio.

    Cripto empieza el 1-ene-2018 con 200 días previos de calentamiento, como `run_study`; bolsa,
    el 1-ene-2008 sobre las sesiones del panel, como `run_etf_study`.
    """
    motor = ficha.motor
    p = panel
    if ficha.mercado == "cripto":
        primera = panel.index_of(motor.inicio)
        p = panel.slice_rows(max(0, primera - CALENTAMIENTO_CRIPTO), len(panel))
    inicio = p.index_of(motor.inicio)
    if inicio >= len(p) - 1:
        raise ValueError(f"no hay datos después del {motor.inicio}")
    config = RunConfig(
        initial_capital=CAPITAL,
        rebalance_every=motor.rebalanceo,
        tranches=motor.tramos,
        no_trade_band=motor.banda,
        start=inicio,
    )
    universo = None if motor.universo is None else PointInTimeUniverse(p, motor.universo)
    copias = [motor.fabrica() for _ in range(motor.tramos)]
    resultado = run(p, copias, motor.costes, config, universo, name=ficha.clave)
    pesos = resultado.weights[inicio:]
    if motor.liquidez is not None and motor.liquidez in p.symbols:
        pesos = np.delete(pesos, p.column(motor.liquidez), axis=1)
    return Recorrido(
        clave=ficha.clave,
        dias=resultado.days[inicio:].copy(),
        valor=resultado.equity[inicio:].copy(),
        invertido=pesos.sum(axis=1),
        operaciones=resultado.trades,
        periodos_al_anio=resultado.periods_per_year,
    )


def cifras(recorrido: Recorrido) -> Cifras:
    """Las cifras en llano de una ejecución (desde su primer día activo)."""
    valor = recorrido.valor
    ppa = recorrido.periodos_al_anio
    anios = max((len(valor) - 1) / ppa, 1e-9)
    inicial, final = float(valor[0]), float(valor[-1])
    crecimiento = (final / inicial) ** (1 / anios) - 1 if inicial > 0 and final > 0 else -1.0
    caidas = drawdown(valor)
    fondo = int(np.argmin(caidas))
    return Cifras(
        desde=recorrido.desde,
        hasta=recorrido.hasta,
        valor_final=final / inicial * CAPITAL,
        crecimiento_anual=crecimiento,
        peor_caida=float(caidas[fondo]),
        peor_caida_fecha=_fecha(int(recorrido.dias[fondo])),
        peor_racha_anios=longest_drawdown(valor) / ppa,
        tiempo_invertido=float(np.mean(recorrido.invertido)),
        operaciones_al_anio=recorrido.operaciones / anios,
    )


class _Memoria:
    """Las ejecuciones de cada mercado, por huella del fichero. Una sola cuenta a la vez."""

    def __init__(self) -> None:
        self._cerrojo = threading.Lock()
        self._guardado: dict[Mercado, tuple[datos.Huella, dict[str, Ejecucion]]] = {}

    def de(self, mercado: Mercado) -> dict[str, Ejecucion]:
        clave = datos.huella(mercado)
        if clave is None:
            motivo = datos.motivo_sin_datos(mercado)
            return {f.clave: Ejecucion(None, motivo) for f in del_mercado(mercado)}
        with self._cerrojo:
            previo = self._guardado.get(mercado)
            if previo is not None and previo[0] == clave:
                return previo[1]
            panel = datos.panel(mercado)
            assert panel is not None  # hay huella: el fichero existe
            calculado = {f.clave: _intentar(f, panel) for f in del_mercado(mercado)}
            self._guardado[mercado] = (clave, calculado)
            return calculado

    def olvidar(self) -> None:
        with self._cerrojo:
            self._guardado.clear()


def _intentar(ficha: Ficha, panel: Panel) -> Ejecucion:
    try:
        return Ejecucion(ejecutar(ficha, panel), None)
    except FALLOS_DE_DATOS as error:
        return Ejecucion(
            None,
            f"Los datos descargados no bastan para calcularla ({error}). Actualízalos con: "
            f"{datos.COMANDOS[ficha.mercado]}",
        )


MEMORIA: Final = _Memoria()


def ejecuciones(mercado: Mercado) -> dict[str, Ejecucion]:
    """Las ejecuciones del mercado: de memoria si los datos no han cambiado."""
    return MEMORIA.de(mercado)


def ejecucion(ficha: Ficha) -> Ejecucion:
    return ejecuciones(ficha.mercado)[ficha.clave]


def precalentar() -> None:
    """Calcula el catálogo entero antes de que nadie lo pida (al arrancar el panel)."""
    for mercado in ("bolsa", "cripto"):
        ejecuciones(mercado)
