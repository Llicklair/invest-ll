"""El examen de un bot antes del dinero real: su regla sobre varios tramos del pasado, cada uno por
separado y frente a solo mantener (docs/panel-v4-real.md §3).

**Por qué no basta una prueba.** Una sola prueba sobre el último año puede salir bien por suerte de
ese año, y más si la regla se diseñó mirándolo (sobreajuste: lo que el README llama «el sistema no
puede mentirte sobre sus propios resultados»). El examen parte el pasado en `TRAMOS` tramos
seguidos y hace correr la regla en cada uno desde cero, con el capital del bot. Una regla que solo
funciona en uno de ellos no aprueba.

**Aprueba si** (las tres cosas):

1. hay al menos `MIN_TRAMOS` tramos con velas;
2. opera lo bastante para decir algo: al menos `MIN_OPERACIONES` operaciones entre todos (con
   menos, el resultado es azar);
3. en al menos dos de cada tres tramos le va como mínimo como a mantener: gana más que mantener, o
   cae menos de la mitad que mantener en su peor momento sin quedarse más de `MARGEN` por detrás.

**Con qué velas.** Las de Binance (contado en USDT), que guarda años; si no tiene alguna de sus
monedas, las de Hyperliquid, que en intervalos cortos solo guarda unas semanas (y entonces hay
menos tramos). Los bots deciden con los precios de Hyperliquid, pero en las monedas grandes son
casi los mismos. Las plantillas que deciden con cada precio (la rejilla) o por calendario (la
periódica) se examinan con el cierre de cada hora: el examen lo dice.

Es la MISMA regla que en vivo (`Plantilla.decidir` o el intérprete de la estrategia a medida) con
el mismo simulador que la prueba de las estrategias (`estrategias_custom.prueba.simular_regla`).
El examen queda en `bots/<id>/examen.json` con la huella de la regla: si la regla cambia, no vale.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from invest_ll import llano
from invest_ll.bots.plantillas import MEDIDA, BotInvalidoError, plantilla
from invest_ll.errors import InvestLLError
from invest_ll.estrategias_custom.formato import DURACION
from invest_ll.exchanges.conector import ExchangeError

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Sequence

    from invest_ll.bots.registro import Definicion
    from invest_ll.estrategias_custom.prueba import Regla, Resultado
    from invest_ll.exchanges.conector import Conector
    from invest_ll.vivo.fuente import Vela

TRAMOS: Final = 6
MIN_TRAMOS: Final = 4
MIN_OPERACIONES: Final = 6
MARGEN: Final = 0.05
"""Cinco puntos: lo que puede quedarse por detrás de mantener si a cambio cae menos de la mitad."""
PERIODO: Final = timedelta(days=360)
VIGENCIA: Final = timedelta(days=30)
"""Un examen más viejo que esto no vale para activar el dinero real: el mercado cambia."""
EXCHANGES: Final = ("binance", "hyperliquid")
INTERVALO_SIN_VELAS: Final = "1h"


class ExamenError(InvestLLError):
    """No se pudo hacer el examen (sin velas, sin las monedas en ningún exchange…)."""


@dataclass(frozen=True, slots=True)
class Tramo:
    desde: datetime
    hasta: datetime
    ganancia_pct: float
    mantener_pct: float
    peor_caida: float
    mantener_peor_caida: float
    operaciones: int

    @property
    def a_favor(self) -> bool:
        """Le fue al menos como a mantener: ganó más, o cayó menos de la mitad sin quedarse más de
        `MARGEN` por detrás."""
        if self.ganancia_pct >= self.mantener_pct:
            return True
        cae_menos = self.peor_caida >= self.mantener_peor_caida / 2
        return cae_menos and self.ganancia_pct >= self.mantener_pct - MARGEN


@dataclass(frozen=True, slots=True)
class Examen:
    firma: str
    """La huella de la regla examinada (plantilla, estrategia, parámetros, monedas)."""
    exchange: str
    intervalo: str
    tramos: tuple[Tramo, ...]
    aprobado: bool
    veredicto: str
    motivos: tuple[str, ...]
    """Por qué no aprueba (vacío si aprueba)."""
    avisos: tuple[str, ...]
    at: datetime

    @property
    def operaciones(self) -> int:
        return sum(t.operaciones for t in self.tramos)

    @property
    def a_favor(self) -> int:
        return sum(1 for t in self.tramos if t.a_favor)

    def vigente(self, firma: str, ahora: datetime) -> bool:
        """Vale para activar: es de esta misma regla y de hace menos de `VIGENCIA`."""
        return self.firma == firma and ahora - self.at <= VIGENCIA


# -- La regla de un bot ----------------------------------------------------------------------------


def regla_del_bot(d: Definicion) -> tuple[Regla, str | None]:
    """La regla con que decide el bot, para el simulador, y el aviso si se examina aproximada."""
    from invest_ll.estrategias_custom.prueba import Regla, regla_de

    if d.plantilla == MEDIDA:
        if not d.estrategia:
            raise BotInvalidoError("El bot es «a medida» pero no dice qué estrategia sigue.")
        from invest_ll.estrategias_custom.biblioteca import CARPETA as CARPETA_MEDIDA
        from invest_ll.estrategias_custom.biblioteca import Biblioteca, EstrategiaNoEncontradaError

        try:
            e = Biblioteca(CARPETA_MEDIDA).ficha(d.estrategia).estrategia
        except EstrategiaNoEncontradaError as error:
            raise BotInvalidoError(str(error)) from error
        return regla_de(e), None
    p = plantilla(d.plantilla)
    parametros = dict(d.parametros)
    intervalo = p.intervalo(parametros)
    aviso = None
    if intervalo is None:
        intervalo = INTERVALO_SIN_VELAS
        aviso = (
            f"«{p.nombre}» decide con cada precio o por calendario: se ha examinado con el cierre "
            "de cada hora, que se parece pero no es lo mismo."
        )
    regla = Regla(
        monedas=tuple(d.monedas),
        intervalo=intervalo,
        necesarias=max(p.velas_necesarias(parametros), 1) + 1,
        decidir=p.decidir,
        huella=_huella({"plantilla": p.clave, "parametros": sorted(parametros.items())}),
        parametros=parametros,
        aplicar=p.aplicar,
    )
    return regla, aviso


def firma_de(d: Definicion, regla: Regla) -> str:
    return _huella(
        {
            "plantilla": d.plantilla,
            "estrategia": d.estrategia,
            "regla": regla.huella,
            "monedas": list(d.monedas),
        }
    )


def _huella(datos: object) -> str:
    texto = json.dumps(datos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:16]


# -- El examen -------------------------------------------------------------------------------------


def _conector_publico(exchange: str) -> Conector:
    from invest_ll.exchanges import registro

    return registro.conector_publico(exchange)


def _velas(
    regla: Regla,
    desde: datetime,
    hasta: datetime,
    conector_publico: Callable[[str], Conector],
) -> tuple[str, dict[str, list[Vela]], Decimal]:
    """Las velas de sus monedas del primer exchange que las tenga todas, y su comisión."""
    from invest_ll.estrategias_custom.prueba import (
        COMISION_POR_DEFECTO,
        PruebaError,
        descargar,
        elegir_mercado,
    )

    fallos: list[str] = []
    for exchange in EXCHANGES:
        try:
            conector = conector_publico(exchange)
            mercados = {c: elegir_mercado(conector, c) for c in regla.monedas}
            velas = {
                c: descargar(conector, m.par, regla.intervalo, desde, hasta)
                for c, m in mercados.items()
            }
        except (PruebaError, ExchangeError) as error:
            fallos.append(f"{exchange}: {error}")
            continue
        if not all(velas.values()):
            fallos.append(f"{exchange}: no da velas de todas sus monedas")
            continue
        comisiones = [m.comision_tomador for m in mercados.values() if m.comision_tomador]
        return exchange, velas, max(comisiones, default=COMISION_POR_DEFECTO)
    raise ExamenError("No se pudieron conseguir las velas para el examen. " + " ".join(fallos))


def examinar(
    d: Definicion,
    *,
    ahora: datetime | None = None,
    conector_publico: Callable[[str], Conector] | None = None,
) -> Examen:
    """Examina la regla del bot sobre el pasado. `ExamenError` en llano si no se puede."""
    from invest_ll.estrategias_custom.prueba import MAX_VELAS, PruebaError, simular_regla

    momento = ahora or datetime.now(UTC)
    regla, aviso_regla = regla_del_bot(d)
    paso = DURACION[regla.intervalo]
    calentar = paso * (regla.necesarias + 1)
    # Lo que cabe en el máximo de velas que se descargan, con su calentamiento.
    periodo = min(PERIODO, paso * (MAX_VELAS - regla.necesarias - 2))
    exchange, velas, comision = _velas(
        regla, momento - periodo - calentar, momento, conector_publico or _conector_publico
    )
    primera = max(serie[0].inicio for serie in velas.values())
    inicio = max(momento - periodo, primera + calentar)
    fin = min(serie[-1].fin for serie in velas.values())
    avisos: list[str] = []
    if aviso_regla:
        avisos.append(aviso_regla)
    if inicio > momento - periodo + timedelta(days=1):
        avisos.append(
            f"{exchange} solo tiene velas de sus monedas desde el "
            f"{llano.fecha_corta(primera.date())}: el examen cubre menos de un año."
        )
    tramos: list[Tramo] = []
    if fin > inicio:
        largo = (fin - inicio) / TRAMOS
        for i in range(TRAMOS):
            desde, hasta = inicio + largo * i, inicio + largo * (i + 1)
            try:
                r = simular_regla(
                    regla,
                    velas,
                    exchange=exchange,
                    capital=d.capital,
                    desde=desde,
                    hasta=hasta,
                    comision=comision,
                    ahora=momento,
                )
            except PruebaError:
                continue
            tramos.append(_tramo(r))
    return _veredicto(firma_de(d, regla), exchange, regla.intervalo, tramos, avisos, momento)


def _tramo(r: Resultado) -> Tramo:
    return Tramo(
        desde=r.desde,
        hasta=r.hasta,
        ganancia_pct=r.ganancia_pct,
        mantener_pct=r.mantener_pct,
        peor_caida=r.peor_caida,
        mantener_peor_caida=r.mantener_peor_caida,
        operaciones=r.operaciones,
    )


def _veredicto(
    firma: str,
    exchange: str,
    intervalo: str,
    tramos: Sequence[Tramo],
    avisos: Sequence[str],
    ahora: datetime,
) -> Examen:
    n = len(tramos)
    a_favor = sum(1 for t in tramos if t.a_favor)
    operaciones = sum(t.operaciones for t in tramos)
    hacen_falta = math.ceil(n * 2 / 3)
    motivos: list[str] = []
    if n < MIN_TRAMOS:
        motivos.append(f"Solo hay {n} tramos con velas y hacen falta {MIN_TRAMOS}.")
    if operaciones < MIN_OPERACIONES:
        motivos.append(
            f"Solo hizo {operaciones} operaciones en todo el examen: con menos de "
            f"{MIN_OPERACIONES} el resultado es azar, no evidencia."
        )
    if n and a_favor < hacen_falta:
        motivos.append(
            f"Solo en {a_favor} de {n} tramos le fue al menos como a mantener (hacen falta "
            f"{hacen_falta})."
        )
    aprobado = not motivos
    if aprobado:
        veredicto = (
            f"Aprobado: en {a_favor} de {n} tramos le fue al menos como a mantener, con "
            f"{operaciones} operaciones."
        )
    else:
        veredicto = "No aprobado. " + " ".join(motivos)
    return Examen(
        firma=firma,
        exchange=exchange,
        intervalo=intervalo,
        tramos=tuple(tramos),
        aprobado=aprobado,
        veredicto=veredicto,
        motivos=tuple(motivos),
        avisos=tuple(avisos),
        at=ahora,
    )


# -- A y desde JSON --------------------------------------------------------------------------------


def a_json(e: Examen) -> dict[str, Any]:
    return {
        "firma": e.firma,
        "exchange": e.exchange,
        "intervalo": e.intervalo,
        "tramos": [
            {
                "desde": t.desde.isoformat(),
                "hasta": t.hasta.isoformat(),
                "ganancia_pct": t.ganancia_pct,
                "mantener_pct": t.mantener_pct,
                "peor_caida": t.peor_caida,
                "mantener_peor_caida": t.mantener_peor_caida,
                "operaciones": t.operaciones,
            }
            for t in e.tramos
        ],
        "aprobado": e.aprobado,
        "veredicto": e.veredicto,
        "motivos": list(e.motivos),
        "avisos": list(e.avisos),
        "at": e.at.isoformat(),
    }


def de_json(d: dict[str, Any]) -> Examen:
    return Examen(
        firma=str(d["firma"]),
        exchange=str(d["exchange"]),
        intervalo=str(d["intervalo"]),
        tramos=tuple(
            Tramo(
                desde=datetime.fromisoformat(t["desde"]),
                hasta=datetime.fromisoformat(t["hasta"]),
                ganancia_pct=float(t["ganancia_pct"]),
                mantener_pct=float(t["mantener_pct"]),
                peor_caida=float(t["peor_caida"]),
                mantener_peor_caida=float(t["mantener_peor_caida"]),
                operaciones=int(t["operaciones"]),
            )
            for t in d["tramos"]
        ),
        aprobado=bool(d["aprobado"]),
        veredicto=str(d["veredicto"]),
        motivos=tuple(str(m) for m in d.get("motivos", [])),
        avisos=tuple(str(a) for a in d.get("avisos", [])),
        at=datetime.fromisoformat(d["at"]),
    )
