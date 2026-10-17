"""Cada estrategia del catálogo ejecutada sobre los datos descargados, con los costes del estudio.

Es la única fuente de las cifras que ve el usuario: lo que hizo con 10.000 desde el principio de
los datos (`Cifras`) y la curva diaria sobre la que se simulan sus aportaciones (`Recorrido`). Se
ejecuta con `invest_ll.quant.engine.run` y la misma configuración que el estudio del 2026-10-16
(`catalogo.Motor`), así que las cifras deben parecerse a las de docs/quant-research.md salvo por
los datos que se hayan descargado después.

Ejecutar el catálogo entero cuesta unos segundos (la cesta prerregistrada, con siete tramos y un
universo de cientos de monedas, es lo más caro), así que se guarda en memoria por la huella del
fichero de datos y cada estrategia se calcula una sola vez aunque lleguen varias peticiones a la
vez. Solo se
guarda lo que el panel usa: la curva y el tiempo invertido de cada día, no la matriz de pesos.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final

import numpy as np

from invest_ll.estrategias import datos
from invest_ll.estrategias.catalogo import CALENTAMIENTO_CRIPTO, FICHAS, del_mercado
from invest_ll.quant.engine import RunConfig, run
from invest_ll.quant.metrics import drawdown, longest_drawdown
from invest_ll.quant.universe import PointInTimeUniverse

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.estrategias.catalogo import Ficha, Mercado
    from invest_ll.quant.panel import FloatArray, IntArray, Panel

CAPITAL: Final = 10_000.0
FALLOS_DE_DATOS = (KeyError, ValueError, IndexError, ZeroDivisionError)
"""Lo que lanza el motor cuando el panel no trae lo que la estrategia necesita (p. ej. SPY)."""

UMBRAL_CAMBIO: Final = 0.10
"""Desde cuánto un cambio del reparto objetivo es "algo que hacer": mover al menos el 10 % del
dinero (la mitad de la suma de las diferencias de peso, contando la liquidez).

Por qué el 10 %: es lo que separa decidir de retocar. Salir de un fondo o de una moneda, entrar, o
cambiar una moneda de la cesta por otra mueve una parte entera del dinero; volver a pesar los
mismos fondos por lo que se mueve cada uno, no. Medido con los datos del 17-10-2026: la paridad de
riesgo sin freno (solo esos retoques) mueve un 3 % de mediana y pasa del 10 % 0,2 veces al año; su
versión con freno, que además saca los fondos que bajan, 8 veces. Por debajo del umbral, el
retoque lo absorben las aportaciones (el plan compra a los pesos de ese día). Un reparto fijo no
cambia nunca su objetivo (sale 0 aunque el motor lo reequilibre por deriva) y Bitcoin con freno
salta del 0 al 100 %: cada entrada y cada salida cuenta una vez.
"""


@dataclass(frozen=True, slots=True)
class Recorrido:
    """Una ejecución, reducida a lo que se enseña. `valor[0]` es el capital inicial."""

    clave: str
    dias: IntArray
    valor: FloatArray
    invertido: FloatArray
    operaciones: int
    periodos_al_anio: int
    cambios: float = 0.0
    """Decisiones que cambian el reparto de forma apreciable, de media por tramo (`Cambios`)."""

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
    cambios_al_anio: float


class Cambios:
    """Cuenta las veces que la estrategia te pediría hacer algo además de aportar.

    Se mira cada tramo por separado, que es como lo viviría quien la siga en su día de la semana
    (o del mes): en cada decisión, cuánto dinero habría que mover para pasar del reparto anterior
    al nuevo (`movido`). Si llega a `umbral`, cuenta. La primera decisión de cada tramo no cuenta:
    es invertir lo que pones al empezar. Al final, la media por tramo (`por_tramo`).

    Con tramos, el motor reparte cada cambio en varios días (un séptimo cada día en Bitcoin con
    freno); contarlos sobre la suma de los tramos diría siete veces lo que hace una persona.
    """

    __slots__ = ("_cuenta", "_previo", "_tramos", "_umbral")

    def __init__(self, tramos: int, umbral: float = UMBRAL_CAMBIO) -> None:
        self._tramos = tramos
        self._umbral = umbral
        self._previo: dict[int, FloatArray] = {}
        self._cuenta = 0

    def __call__(self, tramo: int, fila: int, objetivo: FloatArray) -> None:
        del fila  # solo importa el orden, que es el de las decisiones
        anterior = self._previo.get(tramo)
        if anterior is not None and movido(anterior, objetivo) >= self._umbral:
            self._cuenta += 1
        self._previo[tramo] = objetivo

    @property
    def por_tramo(self) -> float:
        return self._cuenta / self._tramos


def movido(antes: FloatArray, despues: FloatArray) -> float:
    """La parte del dinero que hay que mover para pasar de un reparto a otro (0 a 1).

    La mitad de la suma de las diferencias de peso, contando la liquidez (lo que no suma 1): salir
    del todo de Bitcoin a USDT es mover el 100 %, y cambiar un 20 % de un fondo a otro, el 20 %.
    """
    liquidez = abs((1.0 - float(despues.sum())) - (1.0 - float(antes.sum())))
    return (float(np.abs(despues - antes).sum()) + liquidez) / 2


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
    cambios = Cambios(motor.tramos)
    resultado = run(
        p, copias, motor.costes, config, universo, name=ficha.clave, on_decision=cambios
    )
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
        cambios=cambios.por_tramo,
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
        cambios_al_anio=recorrido.cambios / anios,
    )


class _Memoria:
    """Las ejecuciones de cada mercado, por huella del fichero y estrategia a estrategia.

    Se calcula cada estrategia la primera vez que alguien la pide, y una sola vez aunque lleguen
    varias peticiones a la vez (un cerrojo por mercado). Ir de una en una deja lista antes lo que
    se usa en el camino principal: la recomendación no espera a la cesta de Laboratorio.
    """

    def __init__(self) -> None:
        self._cerrojos: dict[Mercado, threading.Lock] = {
            "bolsa": threading.Lock(),
            "cripto": threading.Lock(),
        }
        self._guardado: dict[Mercado, tuple[datos.Huella, dict[str, Ejecucion]]] = {}

    def de(self, ficha: Ficha) -> Ejecucion:
        mercado = ficha.mercado
        clave = datos.huella(mercado)
        if clave is None:
            return Ejecucion(None, datos.motivo_sin_datos(mercado))
        # Lo ya calculado se sirve sin esperar al cerrojo: mientras se calcula otra estrategia del
        # mismo mercado (la cesta de Laboratorio tarda), las que ya están no deben hacer cola.
        previo = self._guardado.get(mercado)
        if previo is not None and previo[0] == clave and ficha.clave in previo[1]:
            return previo[1][ficha.clave]
        with self._cerrojos[mercado]:
            previo = self._guardado.get(mercado)
            if previo is None or previo[0] != clave:
                previo = (clave, dict[str, Ejecucion]())
                self._guardado[mercado] = previo
            hechas = previo[1]
            if ficha.clave not in hechas:
                panel = datos.panel(mercado)
                assert panel is not None  # hay huella: el fichero existe
                hechas[ficha.clave] = _intentar(ficha, panel)
            return hechas[ficha.clave]

    def olvidar(self) -> None:
        for mercado, cerrojo in self._cerrojos.items():
            with cerrojo:
                self._guardado.pop(mercado, None)


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


def ejecucion(ficha: Ficha) -> Ejecucion:
    """La ejecución de una estrategia: de memoria si los datos no han cambiado."""
    return MEMORIA.de(ficha)


def ejecuciones(mercado: Mercado) -> dict[str, Ejecucion]:
    """Las de todo un mercado, en el orden del catálogo."""
    return {f.clave: ejecucion(f) for f in del_mercado(mercado)}


def precalentar() -> None:
    """Calcula el catálogo antes de que nadie lo pida (al arrancar el panel).

    Primero las del camino principal, que son las que necesitan la recomendación y la primera
    visita a Estrategias; después las de Laboratorio.
    """
    for f in sorted(FICHAS, key=lambda f: not f.principal):
        ejecucion(f)
