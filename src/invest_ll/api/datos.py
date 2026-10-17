"""Datos al día sin abrir una terminal (contrato v2.1).

Una sola actualización trae TODO lo que usa el panel: los históricos de `data/market/<proveedor>/`
(Mercado, Laboratorio), los fondos (`invest-ll-quant download --etf`) y el universo de Binance
(`invest-ll-quant download`), en segundo plano y paso a paso. Solo lee datos públicos de mercado:
nunca envía nada.

- **De cuándo son** (`GET /datos`): el último día de cada fuente y si está al día con la regla de
  `fetch.al_dia` (en bolsa cuenta la última sesión, no el calendario: un lunes, el viernes está al
  día). De los históricos se da el más atrasado: es el que manda.
- **Actualizar** (`POST /datos/actualizar`): un hilo hace los tres pasos en orden y cada uno dice
  cómo va, en llano. Los históricos se re-descargan con los parámetros de su procedencia
  (`fetch_args`, lo mismo que `POST /mercado/actualizar`); los fondos y Binance, con
  `invest-ll-quant download`. Todo con el Python que ya corre (`sys.executable -m ...`), no con
  `uv run`, que intentaría sincronizar el entorno en marcha. Un paso que falla no para los demás.
  Mientras haya una en marcha, otra es un 409.
- **Al terminar** se sueltan las cachés que dependen de los datos (paneles, objetivos, catálogo
  de estrategias, series) y el catálogo se vuelve a calcular en segundo plano, para que la
  siguiente visita a Estrategias no espere ni vea cifras viejas.

`ejecutar` es lo único que lanza procesos (y toca la red): los tests lo sustituyen.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final, Literal

from fastapi import APIRouter

from invest_ll import llano
from invest_ll.api.activos import ILEGIBLE, descargados
from invest_ll.api.errores import conflicto
from invest_ll.api.schemas_v2 import EstadoDatos, FuenteDatos, PasoDatos, TrabajoDatos
from invest_ll.dashboard.data import fetch_args
from invest_ll.estrategias import datos as datos_estrategias
from invest_ll.fetch import al_dia

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

router = APIRouter()

Clave = Literal["historicos", "fondos", "cripto"]
Estado = Literal["pendiente", "en_marcha", "bien", "mal"]

NOMBRES: Final[dict[Clave, str]] = {
    "historicos": "Precios de bolsa y cripto",
    "fondos": "Fondos de las estrategias de bolsa",
    "cripto": "Criptomonedas de las estrategias de Binance",
}
EN_UNA_FRASE: Final[dict[Clave, str]] = {
    "historicos": "los precios de bolsa y cripto",
    "fondos": "los fondos",
    "cripto": "las criptomonedas",
}
QUANT: Final = (sys.executable, "-m", "invest_ll.cli.quant", "download")
TIMEOUT_HISTORICO: Final = 600
"""Segundos por histórico (lo mismo que una descarga de Mercado)."""
TIMEOUT_FONDOS: Final = 900
TIMEOUT_CRIPTO: Final = 3600
"""Binance: cientos de pares, uno a uno. La primera vez, desde 2017; después, solo lo que falta."""
LARGO_DEL_DETALLE: Final = 300


class YaEnMarchaError(RuntimeError):
    """Ya hay una actualización en marcha: otra a la vez descargaría lo mismo dos veces."""


# -- Lo único que lanza procesos (y toca la red): los tests lo sustituyen ----------------------


def ejecutar(argumentos: list[str], *, timeout: int) -> tuple[bool, str]:
    """Lanza un comando y devuelve (si salió bien, lo que dijo)."""
    try:
        proceso = subprocess.run(
            argumentos,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return False, f"no terminó en {timeout} s"
    except OSError as error:
        return False, f"no se pudo lanzar: {error}"
    return proceso.returncode == 0, (proceso.stderr or proceso.stdout or "").strip()


def recalcular() -> None:
    """El catálogo de estrategias, otra vez y antes de que nadie lo pida."""
    from invest_ll.estrategias.historico import precalentar

    precalentar()


# -- De cuándo son los datos ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fuente:
    clave: Clave
    hasta: date | None
    al_dia: bool


def _historicos(hoy: date) -> Fuente:
    """El más atrasado de los históricos sueltos, cada uno con la regla de su mercado."""
    ultimos: list[tuple[date, bool]] = []
    for activo in descargados():
        try:
            serie = activo.load_completa()
        except ILEGIBLE:
            continue
        ultimos.append((serie.bars[-1].timestamp.date(), activo.is_crypto))
    if not ultimos:
        return Fuente("historicos", None, al_dia=False)
    return Fuente(
        "historicos",
        min(d for d, _ in ultimos),
        al_dia=all(al_dia.esta_al_dia(d, hoy, cripto=c) for d, c in ultimos),
    )


def _panel(clave: Clave, hoy: date) -> Fuente:
    mercado: datos_estrategias.Mercado = "bolsa" if clave == "fondos" else "cripto"
    hasta = al_dia.ultimo_dia_del_panel(datos_estrategias.FICHEROS[mercado])
    return Fuente(clave, hasta, al_dia.esta_al_dia(hasta, hoy, cripto=clave == "cripto"))


def fuentes(hoy: date | None = None) -> list[Fuente]:
    """Las tres fuentes que usa el panel, con su último día y si está al día."""
    dia = hoy or al_dia.hoy_utc()
    return [_historicos(dia), _panel("fondos", dia), _panel("cripto", dia)]


def _aviso(viejas: list[Fuente], en_marcha: bool) -> str | None:
    if not viejas:
        return None
    partes = [
        f"{EN_UNA_FRASE[f.clave]} ("
        + ("faltan" if f.hasta is None else f"son del {llano.fecha_corta(f.hasta)}")
        + ")"
        for f in viejas
    ]
    que = "No están al día " + ", ".join(partes) + "."
    if en_marcha:
        return f"{que} Se están actualizando ahora."
    return f"{que} Actualízalos: tarda unos minutos y solo descarga precios, no envía nada."


# -- La actualización, en segundo plano ----------------------------------------------------------


@dataclass(slots=True)
class _Paso:
    clave: Clave
    estado: Estado = "pendiente"
    detalle: str | None = None


@dataclass(slots=True)
class _Trabajo:
    empezado: datetime
    pasos: list[_Paso]
    terminado: datetime | None = None

    @property
    def en_marcha(self) -> bool:
        return self.terminado is None


@dataclass(slots=True)
class _Actualizacion:
    """La última actualización (en curso o hecha). Una por proceso: es el panel de una persona."""

    cerrojo: threading.Lock = field(default_factory=threading.Lock)
    trabajo: _Trabajo | None = None
    hilo: threading.Thread | None = None


ACTUAL: Final = _Actualizacion()


def en_marcha() -> bool:
    with ACTUAL.cerrojo:
        return ACTUAL.trabajo is not None and ACTUAL.trabajo.en_marcha


def lanzar(al_terminar: Callable[[TrabajoDatos], None] | None = None) -> TrabajoDatos:
    """Empieza la actualización en un hilo y devuelve cómo arranca. `YaEnMarchaError` si hay otra.

    `al_terminar` recibe cómo acabó (el lanzador lo cuenta en la consola).
    """
    with ACTUAL.cerrojo:
        if ACTUAL.trabajo is not None and ACTUAL.trabajo.en_marcha:
            raise YaEnMarchaError("ya se están actualizando los datos: espera a que termine")
        trabajo = _Trabajo(
            empezado=datetime.now(UTC),
            pasos=[_Paso("historicos"), _Paso("fondos"), _Paso("cripto")],
        )
        hilo = threading.Thread(
            target=_hacer, args=(trabajo, al_terminar), name="actualizar-datos", daemon=True
        )
        ACTUAL.trabajo, ACTUAL.hilo = trabajo, hilo
        hilo.start()
        return _como_contrato(trabajo)


def esperar(timeout: float | None = None) -> None:
    """Espera a que acabe la actualización en curso (y el catálogo recalculado). Para los tests y
    para quien quiera saber cuándo acaba sin preguntar."""
    hilo = ACTUAL.hilo
    if hilo is not None:
        hilo.join(timeout)


def _marcar(paso: _Paso, estado: Estado, detalle: str | None) -> None:
    with ACTUAL.cerrojo:
        paso.estado, paso.detalle = estado, detalle


def _hacer(trabajo: _Trabajo, al_terminar: Callable[[TrabajoDatos], None] | None) -> None:
    hacer: dict[Clave, Callable[[_Paso], tuple[bool, str]]] = {
        "historicos": _paso_historicos,
        "fondos": lambda paso: _paso_quant(paso, ["--etf"], "fondos", TIMEOUT_FONDOS),
        "cripto": lambda paso: _paso_quant(paso, [], "cripto", TIMEOUT_CRIPTO),
    }
    for paso in trabajo.pasos:
        _marcar(paso, "en_marcha", None)
        try:
            bien, detalle = hacer[paso.clave](paso)
        except Exception as error:  # un paso que revienta no para los demás
            bien, detalle = False, f"Ha fallado algo inesperado: {type(error).__name__}: {error}"
        _marcar(paso, "bien" if bien else "mal", detalle)
    invalidar_caches()
    with ACTUAL.cerrojo:
        trabajo.terminado = datetime.now(UTC)
        final = _como_contrato(trabajo)
    if al_terminar is not None:
        al_terminar(final)
    try:
        recalcular()
    except Exception as error:  # se calculará al pedirlo; aquí solo se adelantaba
        print(f"[!] No se pudo recalcular el catalogo de estrategias: {error}", file=sys.stderr)


def _recorta(texto: str) -> str:
    """El final de lo que dijo un comando, en una línea (lo último es lo que explica el fallo)."""
    una_linea = " ".join(texto.split())
    return una_linea[-LARGO_DEL_DETALLE:] or "sin mensaje"


def _paso_historicos(paso: _Paso) -> tuple[bool, str]:
    ahora = datetime.now(UTC)
    activos = descargados()
    if not activos:
        return True, "No hay precios sueltos descargados: nada que actualizar."
    saltados: list[str] = []
    fallos: list[str] = []
    hechos = 0
    for i, activo in enumerate(activos, start=1):
        _marcar(paso, "en_marcha", f"Actualizando {i} de {len(activos)} ({activo.symbol})…")
        argumentos = fetch_args(activo, hasta=ahora)
        if argumentos is None:
            saltados.append(activo.symbol)
            continue
        bien, salida = ejecutar(argumentos, timeout=TIMEOUT_HISTORICO)
        if bien:
            hechos += 1
        else:
            fallos.append(f"{activo.symbol} ({_recorta(salida)})")
    intentados = len(activos) - len(saltados)
    detalle = f"{hechos} de {intentados} actualizados."
    if fallos:
        detalle += " No se pudo con: " + "; ".join(fallos) + "."
    if saltados:
        detalle += (
            " Sin datos de su descarga original, no se actualizan (se volverían a descargar con "
            "parámetros supuestos): " + ", ".join(saltados) + "."
        )
    return not fallos, detalle


def _paso_quant(paso: _Paso, extra: list[str], clave: Clave, timeout: int) -> tuple[bool, str]:
    _marcar(paso, "en_marcha", "Descargando lo que falta (unos minutos)…")
    bien, salida = ejecutar([*QUANT, *extra], timeout=timeout)
    if not bien:
        return False, f"No se pudo: {_recorta(salida)}"
    hasta = _panel(clave, al_dia.hoy_utc()).hasta
    if hasta is None:
        return False, "Terminó sin dejar datos."
    return True, f"Al día hasta el {llano.fecha_corta(hasta)}."


def invalidar_caches() -> None:
    """Suelta todo lo que se leyó o calculó con los datos de antes."""
    from invest_ll.api.investigacion import olvidar_panel
    from invest_ll.estrategias import historico, objetivo
    from invest_ll.fetch.available import olvidar_series

    datos_estrategias.olvidar()
    objetivo.olvidar()
    historico.MEMORIA.olvidar()
    olvidar_panel()
    olvidar_series()


def _como_contrato(trabajo: _Trabajo) -> TrabajoDatos:
    return TrabajoDatos(
        en_marcha=trabajo.en_marcha,
        empezado=trabajo.empezado,
        terminado=trabajo.terminado,
        pasos=[
            PasoDatos(nombre=NOMBRES[p.clave], estado=p.estado, detalle=p.detalle)
            for p in trabajo.pasos
        ],
    )


def estado(hoy: date | None = None) -> EstadoDatos:
    """Las fuentes, si todo está al día, el aviso en llano y la última actualización."""
    lista = fuentes(hoy)
    dia = hoy or al_dia.hoy_utc()
    with ACTUAL.cerrojo:
        trabajo = None if ACTUAL.trabajo is None else _como_contrato(ACTUAL.trabajo)
    return EstadoDatos(
        fuentes=[
            FuenteDatos(
                clave=f.clave,
                nombre=NOMBRES[f.clave],
                hasta=f.hasta,
                dias=None if f.hasta is None else (dia - f.hasta).days,
                al_dia=f.al_dia,
            )
            for f in lista
        ],
        al_dia=all(f.al_dia for f in lista),
        aviso=_aviso([f for f in lista if not f.al_dia], trabajo is not None and trabajo.en_marcha),
        trabajo=trabajo,
    )


# -- Rutas -----------------------------------------------------------------------------------------


@router.get("/datos", tags=["datos"])
def estado_datos() -> EstadoDatos:
    """De cuándo son los datos que usa el panel y cómo va la última actualización."""
    return estado()


@router.post("/datos/actualizar", tags=["datos"], status_code=202)
def actualizar_datos() -> EstadoDatos:
    """Empieza a actualizarlo todo en segundo plano. 409 si ya hay una actualización en marcha."""
    try:
        lanzar()
    except YaEnMarchaError:
        raise conflicto(
            "Ya se están actualizando los datos: espera a que termine (aquí mismo se ve cómo va)."
        ) from None
    return estado()
