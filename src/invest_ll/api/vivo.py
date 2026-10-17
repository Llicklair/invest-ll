"""Mercado en vivo de Hyperliquid (docs/panel-v3-vivo.md §1 y §5).

Solo lee datos públicos de mercado; no envía nada a ningún exchange. Todo sale de la memoria de la
fuente (`invest_ll.vivo.servicio`), que la conexión mantiene al día en segundo plano: ninguna ruta
espera a la red, salvo `velas` la primera vez que se pide una serie, que espera unos segundos como
mucho a su histórico para no pintar un gráfico vacío.

**El stream** (`GET /api/vivo/stream`, Server-Sent Events) manda en cada evento exactamente el JSON
de su ruta REST, generado por la misma función:

| Evento | Cuándo | `data` |
|---|---|---|
| `monedas` | cada ~1 s | `GET /api/vivo/monedas` |
| `libro` | cada foto nueva del libro de `coin` | `GET /api/vivo/libro?coin=` |
| `operaciones` | cada operación nueva de `coin` | lista de `OperacionMercado`, la más reciente primero |
| `vela` | cada cambio de la vela en curso de `coin` e `intervalo` | `VelaVivo` |
| `cuenta` | cada ~1 s | `GET /api/practica` |
| `bots` | cada ~2 s | `GET /api/bots` (si los bots aún no responden, este canal calla) |
| `estado` | al empezar y al cambiar | `GET /api/vivo/estado` |

Al conectarse llegan enseguida los que son una foto (monedas, libro, vela, cuenta, bots, estado);
`operaciones` solo trae las nuevas (las anteriores, `GET /api/vivo/operaciones`). Cuando la vela en
curso se cierra, llega una última vez (`cerrada: true`) antes de la siguiente. Un comentario
(`: latido`) cada ~15 s mantiene viva la conexión. Si el navegador se va, el stream se corta.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Final

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from invest_ll.api import practica as rutas_practica
from invest_ll.api.errores import invalido, no_encontrado
from invest_ll.api.schemas_v3 import (
    EstadoVivo,
    LibroVivo,
    Monedas,
    MonedaVivo,
    NivelLibro,
    Operaciones,
    OperacionMercado,
    Velas,
    VelaVivo,
)
from invest_ll.nombres import nombre_hyperliquid
from invest_ll.vivo import servicio
from invest_ll.vivo.fuente import INTERVALOS

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import AsyncIterator, Iterable

    from invest_ll.vivo.fuente import Libro, Nivel, Vela
    from invest_ll.vivo.mercado import Mercado, Operacion

log = logging.getLogger(__name__)
router = APIRouter()

CANALES: Final = (
    "monedas",
    "libro",
    "operaciones",
    "vela",
    "cuenta",
    "bots",
    "estado",
    "actividad",
)
DECIMALES_DESCONOCIDOS: Final = 8
"""Si la fuente no dice cuántos decimales admite la cantidad (solo las fuentes de prueba)."""
OPERACIONES_VISIBLES: Final = 50
ESPERA_HISTORICO: Final = 5.0
"""Segundos que `velas` espera, como mucho, al histórico de una serie que se pide por primera vez."""

TICK: Final = 0.1
"""Cada cuánto mira el stream si hay algo nuevo."""
CADA_MONEDAS: Final = 1.0
CADA_CUENTA: Final = 1.0
CADA_BOTS: Final = 2.0
CADA_ACTIVIDAD: Final = 0.5
ACTIVIDAD_AL_CONECTAR: Final = 40
"""Los movimientos que se mandan al conectar (luego, solo los nuevos)."""
LATIDO: Final = 15.0
MAX_EVENTOS: int | None = None
"""Solo para las pruebas: corta el stream tras tantos eventos (el TestClient lee la respuesta
entera antes de devolverla, y un stream que no acaba no se podría probar por HTTP)."""
MAX_SEGUNDOS: float | None = None
"""Solo para las pruebas: corta el stream pasado este tiempo, para que una prueba que espera un
evento que no llega falle en vez de quedarse colgada."""


@router.get("/vivo/estado", tags=["vivo"])
def estado_vivo() -> EstadoVivo:
    """Si llegan datos de Hyperliquid y desde cuándo."""
    estado = servicio.mercado().estado()
    return EstadoVivo(
        conectado=estado.conectada, fuente=estado.fuente, desde=estado.desde, aviso=estado.aviso
    )


@router.get("/vivo/monedas", tags=["vivo"])
def monedas() -> Monedas:
    """Todas las monedas con su precio, variación y volumen de 24 h; las más negociadas primero."""
    mercado = servicio.mercado()
    lista = [
        MonedaVivo(
            coin=info.coin,
            nombre=nombre_hyperliquid(info.coin),
            precio=float(info.precio),
            var_24h=info.variacion_24h,
            volumen_24h=None if info.volumen_24h is None else float(info.volumen_24h),
            decimales_cantidad=(
                DECIMALES_DESCONOCIDOS
                if info.decimales_cantidad is None
                else info.decimales_cantidad
            ),
        )
        for info in mercado.monedas()
        if info.precio is not None
    ]
    return Monedas(
        estado=estado_vivo(), at=mercado.momento_precios() or servicio.ahora(), monedas=lista
    )


@router.get("/vivo/libro", tags=["vivo"])
def libro(coin: str) -> LibroVivo:
    """El libro de órdenes de la moneda (empieza a seguirla si no se seguía). 404 si no existe."""
    mercado = servicio.mercado()
    coin = _moneda(mercado, coin)
    mercado.seguir(coin, libro=True)
    return _libro(coin, mercado.libro(coin))


@router.get("/vivo/operaciones", tags=["vivo"])
def operaciones(coin: str) -> Operaciones:
    """Las últimas operaciones de la moneda."""
    mercado = servicio.mercado()
    coin = _moneda(mercado, coin)
    mercado.seguir(coin, libro=True)
    return Operaciones(
        coin=coin, operaciones=_operaciones(mercado.operaciones(coin, OPERACIONES_VISIBLES))
    )


@router.get("/vivo/velas", tags=["vivo"])
def velas(
    coin: str, intervalo: str = "1h", limite: int = Query(default=300, ge=1, le=5000)
) -> Velas:
    """Velas de la moneda; la última puede estar en curso. 422 si el intervalo no existe."""
    _intervalo(intervalo)
    mercado = servicio.mercado()
    coin = _moneda(mercado, coin)
    mercado.seguir(coin, intervalos=[intervalo])
    _esperar_historico(mercado, coin, intervalo)
    lista = mercado.velas(coin, intervalo, limite)
    return Velas(coin=coin, intervalo=intervalo, velas=[_vela(v) for v in lista])


@router.get("/vivo/stream", tags=["vivo"], response_class=StreamingResponse)
def stream(
    coin: str | None = None,
    intervalo: str = "1h",
    canales: str = "monedas,libro,operaciones,vela,cuenta,bots,estado,actividad",
) -> StreamingResponse:
    """Server-Sent Events: cada evento lleva el JSON de su ruta REST (docs/panel-v3-vivo.md §5)."""
    pedidos = [c.strip() for c in canales.split(",") if c.strip()]
    sobran = [c for c in pedidos if c not in CANALES]
    if sobran or not pedidos:
        raise invalido(
            f"Canales que no existen: {', '.join(sobran) or '(ninguno pedido)'}. "
            f"Valen: {', '.join(CANALES)}."
        )
    _intervalo(intervalo)
    if coin is not None:
        coin = _moneda(servicio.mercado(), coin)
    return StreamingResponse(
        eventos(coin, intervalo, set(pedidos)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# -- El stream ---------------------------------------------------------------------------------------


def evento(nombre: str, datos: BaseModel | list[OperacionMercado]) -> str:
    """Un evento SSE con el JSON tal como lo da la ruta REST (FastAPI serializa en modo JSON y
    sin espacios)."""
    if isinstance(datos, BaseModel):
        crudo: Any = datos.model_dump(mode="json")
    else:
        crudo = [o.model_dump(mode="json") for o in datos]
    texto = json.dumps(crudo, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"event: {nombre}\ndata: {texto}\n\n"


async def eventos(coin: str | None, intervalo: str, canales: set[str]) -> AsyncIterator[str]:
    """Los eventos de un cliente, hasta que se vaya (Starlette cancela esta tarea entonces)."""
    mercado = servicio.mercado()
    if coin is not None:
        mercado.seguir(
            coin,
            libro=bool(canales & {"libro", "operaciones"}),
            intervalos=[intervalo] if "vela" in canales else [],
        )
    reloj = time.monotonic
    ultimo: dict[str, float] = {}
    estado_visto: EstadoVivo | None = None
    libro_visto: Libro | None = None
    vela_vista: Vela | None = None
    vistas = mercado.contador_operaciones(coin) if coin is not None else 0
    latido = empezado = reloj()
    enviados = 0
    actividad_vista: int | None = None

    def toca(canal: str, cada: float) -> bool:
        if canal not in canales or reloj() - ultimo.get(canal, float("-inf")) < cada:
            return False
        ultimo[canal] = reloj()
        return True

    try:
        while True:
            salida: list[str] = []
            if "estado" in canales:
                estado = estado_vivo()
                if estado != estado_visto:
                    salida.append(evento("estado", estado))
                    estado_visto = estado
            if toca("monedas", CADA_MONEDAS):
                salida.append(evento("monedas", monedas()))
            if coin is not None:
                if "libro" in canales:
                    actual = mercado.libro(coin)
                    if actual is not None and actual is not libro_visto:
                        salida.append(evento("libro", _libro(coin, actual)))
                        libro_visto = actual
                if "operaciones" in canales:
                    total = mercado.contador_operaciones(coin)
                    if total > vistas:
                        nuevas = mercado.operaciones(
                            coin, min(total - vistas, OPERACIONES_VISIBLES)
                        )
                        salida.append(evento("operaciones", _operaciones(nuevas)))
                        vistas = total
                if "vela" in canales:
                    for vela in _velas_nuevas(mercado.velas(coin, intervalo, 2), vela_vista):
                        salida.append(evento("vela", _vela(vela)))
                        vela_vista = vela
            if toca("cuenta", CADA_CUENTA):
                salida.append(evento("cuenta", await asyncio.to_thread(rutas_practica.cuenta)))
            if toca("bots", CADA_BOTS):
                bots = await asyncio.to_thread(_bots)
                if bots is not None:
                    salida.append(evento("bots", bots))
            if toca("actividad", CADA_ACTIVIDAD):
                leida = await asyncio.to_thread(actividad_nueva, actividad_vista)
                if leida is not None:
                    actividad_vista, nueva = leida
                    if nueva is not None:
                        salida.append(evento("actividad", nueva))
            for texto in salida:
                yield texto
                enviados += 1
                if MAX_EVENTOS is not None and enviados >= MAX_EVENTOS:
                    return
            if reloj() - latido >= LATIDO:
                yield ": latido\n\n"
                latido = reloj()
            if MAX_SEGUNDOS is not None and reloj() - empezado >= MAX_SEGUNDOS:
                return
            await asyncio.sleep(TICK)
    except asyncio.CancelledError:
        log.debug("Un cliente del stream en vivo se ha ido")
        raise


def _velas_nuevas(ultimas: list[Vela], vista: Vela | None) -> list[Vela]:
    """Lo que hay que mandar de las dos últimas velas: la en curso si cambió y, si empezó otra,
    antes la anterior ya cerrada (por si su último cambio no llegó a mandarse)."""
    if not ultimas:
        return []
    actual = ultimas[-1]
    if vista is None:
        return [actual]
    if actual.inicio > vista.inicio:
        anterior = ultimas[0] if len(ultimas) == 2 else None
        if anterior is not None and anterior.inicio >= vista.inicio and anterior != vista:
            return [anterior, actual]
        return [actual]
    return [actual] if actual != vista else []


def actividad_nueva(vista: int | None) -> tuple[int, BaseModel | None] | None:
    """Lo que el cliente no ha visto del feed de los bots: al conectar (`vista` None), lo último
    que hay (aunque sea nada); luego, solo lo posterior al número `vista`, o nada si no hay nada
    nuevo. None si no hay motor de bots en marcha (el canal calla)."""
    from invest_ll.api import bots as rutas_bots
    from invest_ll.api.schemas_v5 import Actividad
    from invest_ll.bots import motor

    m = motor.activo()
    if m is None:
        return None
    limite = ACTIVIDAD_AL_CONECTAR if vista is None else 200
    numero, lista = m.actividad(desde=vista or 0, limite=limite)
    if vista is not None and not lista:
        return numero, None
    movimientos = [rutas_bots.movimiento(x) for x in lista]
    return numero, Actividad(movimientos=movimientos, inicial=vista is None, at=m.ahora())


def _bots() -> BaseModel | None:
    """`GET /api/bots`, si responde. Lo implementa otra pieza: si aún no está hecha o falla, el
    canal calla y el resto del stream sigue."""
    try:
        from invest_ll.api import bots as rutas_bots

        return rutas_bots.lista()
    except Exception as error:
        log.debug("El canal de bots no emite: %s", error)
        return None


# -- Del dominio al contrato -------------------------------------------------------------------------


def _moneda(mercado: Mercado, coin: str) -> str:
    """El nombre de la moneda tal como lo escribe Hyperliquid; 404 si se sabe que no existe."""
    canonica = mercado.canonica(coin)
    if mercado.existe(canonica) is False:
        raise no_encontrado(f"Hyperliquid no tiene ninguna moneda llamada «{coin}».")
    return canonica


def _intervalo(intervalo: str) -> None:
    if intervalo not in INTERVALOS:
        raise invalido(f"No hay velas de «{intervalo}». Valen: {', '.join(INTERVALOS)}.")


def _esperar_historico(mercado: Mercado, coin: str, intervalo: str) -> None:
    """La primera vez que se pide una serie, su histórico llega por REST en un momento: se
    espera a él (como mucho `ESPERA_HISTORICO`, y solo con conexión) en vez de devolver un
    gráfico vacío. La ruta corre en un hilo aparte: no para el resto del panel."""
    limite_espera = time.monotonic() + ESPERA_HISTORICO
    while (
        mercado.rellenando(coin, intervalo)
        and mercado.conectada()
        and time.monotonic() < limite_espera
    ):
        time.sleep(0.05)


def _libro(coin: str, libro: Libro | None) -> LibroVivo:
    if libro is None:
        # Aún no ha llegado la primera foto (llega en menos de un segundo, también por el stream).
        return LibroVivo(coin=coin, at=servicio.ahora(), compras=[], ventas=[], diferencial=None)
    compra, venta = libro.mejor_compra, libro.mejor_venta
    return LibroVivo(
        coin=coin,
        at=libro.at,
        compras=_niveles(libro.compras),
        ventas=_niveles(libro.ventas),
        diferencial=None if compra is None or venta is None else float(venta - compra),
    )


def _niveles(niveles: Iterable[Nivel]) -> list[NivelLibro]:
    return [
        NivelLibro(precio=float(n.precio), cantidad=float(n.cantidad), ordenes=n.ordenes)
        for n in niveles
    ]


def _operaciones(lista: Iterable[Operacion]) -> list[OperacionMercado]:
    return [
        OperacionMercado(
            coin=o.coin, at=o.at, precio=float(o.precio), cantidad=float(o.cantidad), lado=o.lado
        )
        for o in lista
    ]


def _vela(v: Vela) -> VelaVivo:
    return VelaVivo(
        coin=v.coin,
        intervalo=v.intervalo,
        inicio=v.inicio,
        apertura=float(v.apertura),
        maximo=float(v.maximo),
        minimo=float(v.minimo),
        cierre=float(v.cierre),
        volumen=float(v.volumen),
        cerrada=v.cerrada,
    )
