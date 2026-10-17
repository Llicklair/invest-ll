"""Pestaña Mercado: ¿cómo está el mundo? Rendimiento, gráficas, comparación y estado de los datos.

Es deliberadamente aburrida comparada con un panel de mercado al uso: no hay indicadores de "miedo
y codicia" ni "temporada de altcoins". Esos indicadores existen para que operes más, y todo lo
medido en este proyecto dice que operar más pierde dinero.

Las tres rutas que tocan la red o lanzan procesos (`cotizaciones`, `descargar`, `actualizar`)
pasan por `pedir_cripto`, `pedir_bolsa` y `ejecutar_fetch`, que los tests sustituyen: la suite
corre sin red a propósito.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query

from invest_ll.alerts.rules import datos_obsoletos
from invest_ll.api.activos import (
    ILEGIBLE,
    descargados,
    por_simbolo,
    resolver_varios,
    serie_completa,
)
from invest_ll.api.errores import invalido
from invest_ll.api.schemas import (
    Comparacion,
    Cotizacion,
    Cotizaciones,
    DatosDescargados,
    FilaDatos,
    FilaRendimiento,
    PeticionDescarga,
    Punto,
    PuntoComparado,
    Rendimiento,
    ResultadoActualizacion,
    ResultadoDescarga,
    Serie,
    Tramo,
)
from invest_ll.dashboard.data import (
    VENTANAS,
    fetch_args,
    full_history_args,
    market_overview,
    normalised_series,
)
from invest_ll.fetch.available import desde_hace
from invest_ll.fetch.catalog import EQUITY_CATALOG
from invest_ll.fetch.live import LiveDataError, crypto_tickers, equity_quotes
from invest_ll.nombres import moneda_de, nombre_llano

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.fetch.live import LiveQuote

router = APIRouter()

DIAS_POR_TRAMO: dict[str, int | None] = {"3m": 91, "1a": 365, "5a": 1826, "todo": None}
"""Días naturales de cada tramo de la gráfica: en velas, el "1 año" de la cripto (que cotiza los
fines de semana) eran ocho meses y medio."""

TIMEOUT_DESCARGA = 600
"""Segundos que se espera a una descarga antes de darla por fallida."""

# Las columnas de `market_overview` (pensadas para una tabla) y su nombre en el contrato. Las
# variaciones y la distancia al maximo van en PORCENTAJE (12.3 = +12,3%), como las calcula alli.
COLUMNAS_RENDIMIENTO = {
    "activo": "activo",
    "que es": "que_es",
    "ultimo": "ultimo",
    "1 dia": "var_1d",
    "1 semana": "var_1s",
    "1 mes": "var_1m",
    "3 meses": "var_3m",
    "YTD": "ytd",
    "1 año": "var_1a",
    "5 años": "var_5a",
    "desde maximo": "desde_maximo",
    "sparkline": "sparkline",
    "desde": "desde",
    "datos hasta": "datos_hasta",
}


# -- Lo que toca la red o lanza procesos: aislado para poder sustituirlo en los tests ----------


def pedir_cripto() -> list[LiveQuote]:
    """Todos los pares USDT al contado de Binance. Toca la red."""
    return crypto_tickers()


def pedir_bolsa() -> list[LiveQuote]:
    """El catálogo de bolsa en yfinance. Toca la red."""
    return equity_quotes(EQUITY_CATALOG)


def ejecutar_fetch(argumentos: list[str]) -> tuple[bool, str]:
    """Lanza `invest-ll-fetch` y devuelve (si salió bien, lo que dijo). Toca la red."""
    try:
        proceso = subprocess.run(
            argumentos,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_DESCARGA,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )
    except subprocess.TimeoutExpired:
        return False, f"la descarga no termino en {TIMEOUT_DESCARGA} s"
    except OSError as error:
        return False, f"no se pudo lanzar la descarga: {error}"
    return proceso.returncode == 0, (proceso.stderr or proceso.stdout or "").strip()


# -- Rutas -------------------------------------------------------------------------------------


@router.get("/mercado/rendimiento", tags=["mercado"])
def rendimiento() -> Rendimiento:
    """La mesa densa por periodo, separada en bolsa y cripto (`market_overview`)."""
    bolsa: list[FilaRendimiento] = []
    cripto: list[FilaRendimiento] = []
    for activo in descargados():
        for fila in market_overview([activo]):
            modelo = FilaRendimiento.model_validate(
                {
                    **{campo: fila[columna] for columna, campo in COLUMNAS_RENDIMIENTO.items()},
                    "nombre": nombre_llano(activo.symbol),
                    "moneda": moneda_de(activo.symbol),
                }
            )
            (cripto if activo.is_crypto else bolsa).append(modelo)
    return Rendimiento(bolsa=bolsa, cripto=cripto)


@router.get("/mercado/serie", tags=["mercado"])
def serie(symbol: str, tramo: Tramo = "1a") -> Serie:
    """Cierres de un activo para su gráfica. 404 si no hay histórico de ese símbolo."""
    activo = por_simbolo(symbol)
    completa = serie_completa(activo)
    dias = DIAS_POR_TRAMO[tramo]
    inicio = desde_hace(completa.bars, dias) if dias else None
    barras = completa.bars[inicio or 0 :]
    return Serie(
        symbol=activo.symbol,
        tramo=tramo,
        puntos=[Punto(fecha=b.timestamp, valor=b.close) for b in barras],
        sesiones=len(barras),
        hasta=completa.bars[-1].timestamp.date(),
    )


@router.get("/mercado/comparacion", tags=["mercado"])
def comparacion(
    activos: list[str] = Query(description="Ids de activos"),  # noqa: B008
    ventana: str | None = Query(default=None, description="'1 mes', '3 meses', '1 año', '5 años'"),
) -> Comparacion:
    """Base 100 al inicio del tramo (`normalised_series`); sin ventana, todo el histórico común."""
    ventanas = dict(VENTANAS)
    periodos: int | None = None
    if ventana is not None:
        if ventana not in ventanas:
            raise invalido(
                f"ventana desconocida {ventana!r}; opciones: {', '.join(ventanas)} "
                "(o ninguna, para todo el historico)"
            )
        periodos = ventanas[ventana]
    seleccion = resolver_varios(activos)
    puntos = [
        PuntoComparado.model_validate(p) for p in normalised_series(seleccion, periods=periodos)
    ]
    return Comparacion(puntos=puntos)


@router.get("/mercado/datos", tags=["mercado"])
def datos() -> DatosDescargados:
    """Último cierre de cada histórico descargado, y cuáles están desfasados."""
    ahora = datetime.now(UTC)
    filas: list[FilaDatos] = []
    desfasados: list[str] = []
    for activo in descargados():
        try:
            completa = activo.load_completa()
        except ILEGIBLE:
            continue
        ultimo = completa.bars[-1]
        previo = completa.bars[-2] if len(completa) > 1 else ultimo
        filas.append(
            FilaDatos(
                activo=activo.symbol,
                ultimo_cierre=ultimo.close,
                variacion=(ultimo.close / previo.close - 1) if previo.close else 0.0,
                fecha=ultimo.timestamp.date(),
                velas=len(completa),
                descargado=(activo.provenance.downloaded_at.date() if activo.provenance else None),
            )
        )
        # La misma vara que la alerta de datos obsoletos, no una fecha fija escrita a mano.
        if datos_obsoletos(completa, ahora=ahora) is not None:
            desfasados.append(activo.symbol)
    return DatosDescargados(filas=filas, desfasados=desfasados)


def _fila_viva(cotizacion: LiveQuote, descargados_: set[str]) -> Cotizacion:
    return Cotizacion(
        activo=cotizacion.symbol,
        precio=cotizacion.price,
        var_24h=cotizacion.change_24h_pct,
        volumen_24h_m=(
            round(cotizacion.volume_24h / 1_000_000, 2)
            if cotizacion.volume_24h is not None
            else None
        ),
        descargado=cotizacion.symbol in descargados_,
    )


@router.post("/mercado/cotizaciones", tags=["mercado"])
def cotizaciones() -> Cotizaciones:
    """Foto al pulsar de Binance (pares USDT) y del catálogo de bolsa. Toca la red."""
    ya_descargados = {a.symbol for a in descargados()}
    errores: list[str] = []
    at = datetime.now(UTC)

    try:
        cripto = [_fila_viva(q, ya_descargados) for q in pedir_cripto()]
    except LiveDataError as error:
        cripto = []
        errores.append(f"Cripto: {error}")
    try:
        bolsa = [_fila_viva(q, ya_descargados) for q in pedir_bolsa()]
    except LiveDataError as error:
        bolsa = []
        errores.append(f"Bolsa: {error}")

    return Cotizaciones(at=at, bolsa=bolsa, cripto=cripto, errores=errores)


@router.post("/mercado/descargar", tags=["mercado"])
def descargar(peticion: PeticionDescarga) -> ResultadoDescarga:
    """Descarga el histórico completo (desde 2015) de un activo con `invest-ll-fetch`."""
    simbolo = peticion.symbol.strip()
    if not simbolo or simbolo.startswith("-"):
        # Un "simbolo" que empieza por guion llegaria a invest-ll-fetch como una opcion.
        raise invalido(f"simbolo no valido: {peticion.symbol!r}")

    if simbolo in {a.symbol for a in descargados()}:
        return ResultadoDescarga(
            symbol=simbolo,
            ok=True,
            detalle=(
                f"{simbolo} ya tiene historico descargado: lo tienes en las mesas de rendimiento, "
                "con su grafica. Para alargarlo, actualiza los historicos."
            ),
        )

    argumentos = full_history_args(simbolo, market=peticion.mercado, hasta=datetime.now(UTC))
    bien, salida = ejecutar_fetch(argumentos)
    if bien:
        detalle = f"{simbolo} descargado: ya aparece en las mesas de rendimiento."
    else:
        detalle = f"No se pudo descargar {simbolo}: {salida[-300:] or 'sin mensaje'}"
    return ResultadoDescarga(symbol=simbolo, ok=bien, detalle=detalle)


@router.post("/mercado/actualizar", tags=["mercado"])
def actualizar() -> ResultadoActualizacion:
    """Re-descarga todos los históricos con los parámetros de su procedencia (`fetch_args`)."""
    ahora = datetime.now(UTC)
    resultados: list[ResultadoDescarga] = []
    saltados: list[str] = []
    for activo in descargados():
        argumentos = fetch_args(activo, hasta=ahora)
        if argumentos is None:
            saltados.append(activo.symbol)
            continue
        bien, salida = ejecutar_fetch(argumentos)
        detalle = salida[-200:] or ("actualizado" if bien else "sin mensaje")
        resultados.append(ResultadoDescarga(symbol=activo.symbol, ok=bien, detalle=detalle))
    return ResultadoActualizacion(resultados=resultados, saltados=saltados)
