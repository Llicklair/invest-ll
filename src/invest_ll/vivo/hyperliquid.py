"""Hyperliquid sin red: cómo se leen sus mensajes y dónde se guarda lo último que se sabe.

Hyperliquid es un exchange con libro de órdenes propio y una API pública de datos de mercado, sin
cuenta ni claves (docs/panel-v3-vivo.md §1). Este módulo **no toca la red**: la conexión
(`vivo/red.py`, el único que sale) le pasa lo que llega y le pregunta qué tiene que pedir. Así todo
lo que interpreta los mensajes se prueba con mensajes reales guardados
(`tests/fixtures/hyperliquid/`), sin conexión.

Formas de los mensajes (verificadas contra la documentación oficial y contra el servicio, oct 2026):

- `allMids`: `{"BTC": "81180.5", ...}` (REST) o `{"mids": {...}}` (WebSocket). Trae también los
  mercados al contado (`PURR/USDC`, `@107`) y los de predicción (`#114220`): solo valen los nombres
  de los perpetuos.
- `l2Book`: `{"coin", "time" (ms), "levels": [compras, ventas]}`, cada nivel `{"px", "sz", "n"}`,
  como mucho 20 por lado; compras de mayor a menor precio, ventas de menor a mayor.
- `trades`: lista de `{"coin", "side" ("B" compra, "A" venta: el lado de quien inició), "px", "sz",
  "time", "tid", ...}`; el primer mensaje trae las 30 últimas, de la más antigua a la más reciente.
- `candle` y `candleSnapshot`: `{"t" (inicio, ms), "T" (último ms), "s", "i", "o", "c", "h", "l",
  "v" (volumen en la moneda), "n"}`.
- `metaAndAssetCtxs`: `[{"universe": [{"name", "szDecimals", "isDelisted"?...}]}, [{"prevDayPx",
  "dayNtlVlm", "midPx", "markPx", ...}, ...]]`, un contexto por moneda en el mismo orden.

**Ojo**: suscribirse por WebSocket a una moneda que no existe hace que Hyperliquid cierre la
conexión entera. Por eso solo se piden monedas que están en su lista.

Lo que se guarda en memoria tiene límite: `MAX_VELAS` por serie (las que Hyperliquid da como mucho),
`MAX_OPERACIONES` por moneda y `MAX_SEGUIDAS` monedas y series seguidas.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.vivo.fuente import INTERVALOS, Libro, Nivel, Vela
from invest_ll.vivo.mercado import EstadoConexion, InfoMoneda, Operacion

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Iterable, Mapping, Sequence

log = logging.getLogger(__name__)

URL_INFO: Final = "https://api.hyperliquid.xyz/info"
URL_WS: Final = "wss://api.hyperliquid.xyz/ws"

MAX_VELAS: Final = 5000
"""Por serie: las que Hyperliquid da como mucho (`candleSnapshot`)."""
MAX_OPERACIONES: Final = 200
"""Por moneda: las últimas del mercado."""
MAX_SEGUIDAS: Final = 100
"""Monedas con libro y series de velas seguidas, cada una (Hyperliquid admite 1000 suscripciones
por IP; un panel no necesita más)."""
SIN_NOTICIAS: Final = 20.0
"""Segundos sin ningún mensaje para dejar de dar la conexión por viva (`allMids` llega cada ~5 s)."""

DURACION: Final[dict[str, timedelta]] = {
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "1M": timedelta(days=31),
}
"""Lo que dura cada vela (el mes, por arriba): para saber desde cuándo pedir el histórico."""
ANTES_DE_HYPERLIQUID: Final = datetime(2023, 1, 1, tzinfo=UTC)
"""El histórico se pide como mucho desde aquí (5000 velas semanales serían casi un siglo)."""

_PERPETUO = re.compile(r"^[A-Za-z0-9]+$")
"""Los perpetuos se llaman con letras y cifras; lo demás de `allMids` es contado o predicción."""


class MensajeRaroError(ValueError):
    """Un mensaje de Hyperliquid que no tiene la forma esperada."""


# -- Interpretar mensajes (puro) -------------------------------------------------------------------


def _decimal(valor: object) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        cifra = Decimal(str(valor))
    except InvalidOperation:
        return None
    return cifra if cifra.is_finite() else None


def _decimal_obligatorio(valor: object, que: str) -> Decimal:
    cifra = _decimal(valor)
    if cifra is None:
        raise MensajeRaroError(f"{que} no es un número: {valor!r}")
    return cifra


def hora(ms: object) -> datetime:
    """Los milisegundos de Hyperliquid como fecha con zona (UTC)."""
    if not isinstance(ms, int | float) or isinstance(ms, bool):
        raise MensajeRaroError(f"hora no válida: {ms!r}")
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def ms(momento: datetime) -> int:
    return int(momento.timestamp() * 1000)


def es_perpetuo(coin: str) -> bool:
    return bool(_PERPETUO.match(coin))


def leer_mids(datos: Mapping[str, Any]) -> dict[str, Decimal]:
    """Los precios medios de los perpetuos, de `allMids` (REST o el `data` del WebSocket)."""
    crudos = datos.get("mids", datos)
    if not isinstance(crudos, dict):
        raise MensajeRaroError("allMids sin precios")
    mids: dict[str, Decimal] = {}
    for coin, texto in cast("dict[str, object]", crudos).items():
        precio = _decimal(texto)
        if es_perpetuo(coin) and precio is not None and precio > 0:
            mids[coin] = precio
    return mids


def leer_meta(respuesta: Sequence[Any]) -> dict[str, InfoMoneda]:
    """`metaAndAssetCtxs`: decimales, precio de hace 24 h y volumen de cada moneda en activo.

    Las retiradas (`isDelisted`) no se devuelven: no se pueden negociar.
    """
    if len(respuesta) != 2:
        raise MensajeRaroError("metaAndAssetCtxs no trae [meta, contextos]")
    meta: object = respuesta[0]
    crudos: object = respuesta[1]
    lista: object = cast("dict[str, Any]", meta).get("universe") if isinstance(meta, dict) else None
    if not isinstance(lista, list) or not isinstance(crudos, list):
        raise MensajeRaroError("metaAndAssetCtxs sin universo o sin contextos")
    universo = cast("list[dict[str, Any]]", lista)
    contextos = cast("list[dict[str, Any] | None]", crudos)
    if len(universo) != len(contextos):
        raise MensajeRaroError("metaAndAssetCtxs con universo y contextos de distinto tamaño")
    info: dict[str, InfoMoneda] = {}
    for entrada, contexto in zip(universo, contextos, strict=True):
        coin = entrada.get("name")
        if not isinstance(coin, str) or entrada.get("isDelisted"):
            continue
        ctx: dict[str, Any] = contexto or {}
        decimales = entrada.get("szDecimals")
        info[coin] = InfoMoneda(
            coin=coin,
            decimales_cantidad=decimales if isinstance(decimales, int) else None,
            precio=_decimal(ctx.get("midPx")) or _decimal(ctx.get("markPx")),
            precio_ayer=_decimal(ctx.get("prevDayPx")),
            volumen_24h=_decimal(ctx.get("dayNtlVlm")),
        )
    return info


def _niveles(crudos: object) -> tuple[Nivel, ...]:
    if not isinstance(crudos, list):
        raise MensajeRaroError("lado del libro no válido")
    niveles: list[Nivel] = []
    for crudo in cast("list[dict[str, Any]]", crudos):
        ordenes = crudo.get("n", 1)
        niveles.append(
            Nivel(
                precio=_decimal_obligatorio(crudo.get("px"), "precio del libro"),
                cantidad=_decimal_obligatorio(crudo.get("sz"), "cantidad del libro"),
                ordenes=ordenes if isinstance(ordenes, int) else 1,
            )
        )
    return tuple(niveles)


def leer_libro(datos: Mapping[str, Any]) -> Libro:
    """`l2Book` (REST o el `data` del WebSocket): compras de mayor a menor, ventas de menor a mayor."""
    niveles = datos.get("levels")
    coin = datos.get("coin")
    if not isinstance(coin, str) or not isinstance(niveles, list):
        raise MensajeRaroError("l2Book sin moneda o sin niveles")
    lados = cast("list[object]", niveles)
    if len(lados) != 2:
        raise MensajeRaroError("l2Book sin sus dos lados")
    compras = tuple(sorted(_niveles(lados[0]), key=lambda n: n.precio, reverse=True))
    ventas = tuple(sorted(_niveles(lados[1]), key=lambda n: n.precio))
    return Libro(coin=coin, compras=compras, ventas=ventas, at=hora(datos.get("time")))


def leer_operaciones(datos: Sequence[Any]) -> list[Operacion]:
    """`trades`: en el orden en que llegan (de la más antigua a la más reciente)."""
    operaciones: list[Operacion] = []
    for crudo in cast("Sequence[dict[str, Any]]", datos):
        lado = crudo.get("side")
        if lado not in ("A", "B"):
            raise MensajeRaroError(f"lado de operación no válido: {lado!r}")
        tid = crudo.get("tid")
        operaciones.append(
            Operacion(
                coin=str(crudo.get("coin")),
                at=hora(crudo.get("time")),
                precio=_decimal_obligatorio(crudo.get("px"), "precio de la operación"),
                cantidad=_decimal_obligatorio(crudo.get("sz"), "cantidad de la operación"),
                lado="compra" if lado == "B" else "venta",
                id=tid if isinstance(tid, int) else 0,
            )
        )
    return operaciones


def leer_vela(datos: Mapping[str, Any], *, cerrada: bool = False) -> Vela:
    """Una vela (`candle` o un elemento de `candleSnapshot`). `fin` es el primer milisegundo
    de la siguiente; si está cerrada lo decide quien la guarda, que sabe cuál es la última."""
    intervalo = datos.get("i")
    coin = datos.get("s")
    if not isinstance(coin, str) or intervalo not in INTERVALOS:
        raise MensajeRaroError("vela sin moneda o con un intervalo desconocido")
    ultimo = datos.get("T")
    if not isinstance(ultimo, int):
        raise MensajeRaroError("vela sin hora de cierre")
    return Vela(
        coin=coin,
        intervalo=str(intervalo),
        inicio=hora(datos.get("t")),
        fin=hora(ultimo + 1),
        apertura=_decimal_obligatorio(datos.get("o"), "apertura"),
        maximo=_decimal_obligatorio(datos.get("h"), "máximo"),
        minimo=_decimal_obligatorio(datos.get("l"), "mínimo"),
        cierre=_decimal_obligatorio(datos.get("c"), "cierre"),
        volumen=_decimal_obligatorio(datos.get("v"), "volumen"),
        cerrada=cerrada,
    )


# -- Lo que se pide (puro) -------------------------------------------------------------------------

Suscripcion = tuple[Literal["allMids", "l2Book", "trades", "candle"], str, str]
"""(tipo, moneda, intervalo): la forma con la que se recuerda qué se ha pedido."""


def mensaje_suscripcion(suscripcion: Suscripcion) -> dict[str, Any]:
    """El mensaje del WebSocket para suscribirse. El libro, con `fast` (una foto cada ~0,5 s en
    vez de cada ~5 s)."""
    tipo, coin, intervalo = suscripcion
    datos: dict[str, Any] = {"type": tipo}
    if tipo == "l2Book":
        datos |= {"coin": coin, "fast": True}
    elif tipo == "trades":
        datos["coin"] = coin
    elif tipo == "candle":
        datos |= {"coin": coin, "interval": intervalo}
    return {"method": "subscribe", "subscription": datos}


def peticion_velas(coin: str, intervalo: str, desde: datetime, hasta: datetime) -> dict[str, Any]:
    """El cuerpo de `candleSnapshot`."""
    return {
        "type": "candleSnapshot",
        "req": {"coin": coin, "interval": intervalo, "startTime": ms(desde), "endTime": ms(hasta)},
    }


PETICION_META: Final[dict[str, Any]] = {"type": "metaAndAssetCtxs"}
PETICION_MIDS: Final[dict[str, Any]] = {"type": "allMids"}


# -- La fuente en memoria --------------------------------------------------------------------------


def _ahora() -> datetime:
    return datetime.now(UTC)


class FuenteHyperliquid:
    """`FuentePrecios` (y `Mercado`) con lo que llega de Hyperliquid. No toca la red.

    La conexión le pasa cada mensaje (`recibir`, `recibir_meta`, `recibir_velas`), le dice cuándo
    abre y cierra (`abierta`, `cerrada`) y le pregunta qué tiene que pedir (`suscripciones`,
    `por_rellenar`). `seguir` se puede llamar desde cualquier hilo: apunta lo que se quiere y avisa
    a la conexión con `al_seguir`. Todo lo demás responde al momento con lo que hay en memoria.
    """

    def __init__(
        self,
        *,
        reloj: Callable[[], datetime] = _ahora,
        monotono: Callable[[], float] = time.monotonic,
        aviso_inicial: str = "Conectando con Hyperliquid…",
    ) -> None:
        self._reloj = reloj
        self._monotono = monotono
        self._aviso_inicial = aviso_inicial
        self._cerrojo = threading.RLock()
        self.al_seguir: Callable[[], None] | None = None
        """Lo llama `seguir` cuando hay algo nuevo que pedir (la conexión lo pone)."""

        self._mids: dict[str, Decimal] = {}
        self._mids_at: datetime | None = None
        self._mids_recibidos = float("-inf")
        self._info: dict[str, InfoMoneda] = {}
        self._libros: dict[str, Libro] = {}
        self._libros_recibidos: dict[str, float] = {}
        self._operaciones: dict[str, deque[Operacion]] = {}
        self._contador: dict[str, int] = {}
        self._series: dict[tuple[str, str], dict[int, tuple[Vela, float]]] = {}
        self._ultima: dict[tuple[str, str], int] = {}

        self._libros_seguidos: set[str] = set()
        self._series_seguidas: set[tuple[str, str]] = set()
        self._por_rellenar: set[tuple[str, str]] = set()
        self._rellenando: set[tuple[str, str]] = set()
        self._rellenar_desde: dict[tuple[str, str], int] = {}

        self._abierta = False
        self._ultimo_mensaje = float("-inf")
        self._desde: datetime | None = None
        self._cerrada_en: datetime | None = None
        self._motivo: str | None = None
        self._intentos = 0

    # -- FuentePrecios -----------------------------------------------------------------------------

    def conectada(self) -> bool:
        with self._cerrojo:
            return self._abierta and self._monotono() - self._ultimo_mensaje < SIN_NOTICIAS

    def seguir(self, coin: str, *, libro: bool = False, intervalos: Iterable[str] = ()) -> None:
        coin = self.canonica(coin)
        nuevos = False
        with self._cerrojo:
            if self._existe(coin) is False:
                return
            if libro and coin not in self._libros_seguidos:
                if len(self._libros_seguidos) < MAX_SEGUIDAS:
                    self._libros_seguidos.add(coin)
                    nuevos = True
                else:
                    log.warning("Ya se siguen %s libros: no se sigue el de %s", MAX_SEGUIDAS, coin)
            for intervalo in intervalos:
                serie = (coin, intervalo)
                if intervalo not in INTERVALOS or serie in self._series_seguidas:
                    continue
                if len(self._series_seguidas) >= MAX_SEGUIDAS:
                    log.warning(
                        "Ya se siguen %s series de velas: no se sigue %s", MAX_SEGUIDAS, serie
                    )
                    continue
                self._series_seguidas.add(serie)
                self._por_rellenar.add(serie)
                nuevos = True
        if nuevos and self.al_seguir is not None:
            self.al_seguir()

    def precio(self, coin: str) -> Decimal | None:
        """El más reciente entre el medio del libro (si se sigue, cada ~0,5 s) y el de la lista
        de precios (cada ~5 s)."""
        with self._cerrojo:
            libro = self._libros.get(coin)
            medio = libro.medio if libro is not None else None
            if medio is not None and self._libros_recibidos.get(coin, 0) >= self._mids_recibidos:
                return medio
            if coin in self._mids:
                return self._mids[coin]
            if medio is not None:
                return medio
            info = self._info.get(coin)
            return info.precio if info is not None else None

    def libro(self, coin: str) -> Libro | None:
        with self._cerrojo:
            return self._libros.get(coin)

    def velas(self, coin: str, intervalo: str, limite: int = 500) -> list[Vela]:
        """Todas cerradas salvo, quizá, la última: esa lo está si ya pasó su hora de cierre."""
        ahora = self._reloj()
        with self._cerrojo:
            serie = self._series.get((coin, intervalo))
            if not serie or limite <= 0:
                return []
            velas = [serie[t][0] for t in sorted(serie)[-limite:]]
        if not velas[-1].cerrada and velas[-1].fin <= ahora:
            velas[-1] = replace(velas[-1], cerrada=True)
        return velas

    # -- Mercado -----------------------------------------------------------------------------------

    def estado(self) -> EstadoConexion:
        with self._cerrojo:
            conectada = self.conectada()
            if conectada:
                return EstadoConexion(conectada=True, desde=self._desde, aviso=None)
            if self._abierta:
                aviso = "Hyperliquid no manda datos desde hace un rato; se reconecta solo."
            elif self._cerrada_en is None and self._intentos == 0:
                aviso = self._aviso_inicial
            else:
                aviso = "Sin conexión con Hyperliquid"
                if self._cerrada_en is not None:
                    aviso += f" desde las {self._cerrada_en.astimezone():%H:%M:%S}"
                aviso += (
                    f"; se reintenta solo (intento {self._intentos}). Los precios que ves pueden "
                    "estar viejos."
                )
            return EstadoConexion(conectada=False, desde=None, aviso=aviso)

    def existe(self, coin: str) -> bool | None:
        with self._cerrojo:
            return self._existe(self.canonica(coin))

    def _existe(self, coin: str) -> bool | None:
        if self._info:
            return coin in self._info
        if self._mids:
            return coin in self._mids
        return None

    def canonica(self, coin: str) -> str:
        coin = coin.strip()
        with self._cerrojo:
            if coin in self._info or coin in self._mids:
                return coin
            for conocida in (*self._info, *self._mids):
                if conocida.lower() == coin.lower():
                    return conocida
        return coin

    def monedas(self) -> list[InfoMoneda]:
        with self._cerrojo:
            nombres = list(self._info) if self._info else list(self._mids)
            lista = [self._info_de(coin) for coin in nombres]
        return sorted(lista, key=lambda i: (i.volumen_24h is None, -(i.volumen_24h or 0), i.coin))

    def _info_de(self, coin: str) -> InfoMoneda:
        info = self._info.get(coin)
        precio = self.precio(coin)
        if info is None:
            return InfoMoneda(coin, None, precio, None, None)
        return InfoMoneda(
            coin=coin,
            decimales_cantidad=info.decimales_cantidad,
            precio=precio,
            precio_ayer=info.precio_ayer,
            volumen_24h=info.volumen_24h,
        )

    def momento_precios(self) -> datetime | None:
        with self._cerrojo:
            return self._mids_at

    def decimales(self, coin: str) -> int | None:
        with self._cerrojo:
            info = self._info.get(coin)
            return info.decimales_cantidad if info is not None else None

    def operaciones(self, coin: str, limite: int = 50) -> list[Operacion]:
        with self._cerrojo:
            todas = self._operaciones.get(coin)
            if not todas:
                return []
            return list(reversed(todas))[:limite]

    def contador_operaciones(self, coin: str) -> int:
        with self._cerrojo:
            return self._contador.get(coin, 0)

    # -- Lo que llama la conexión ------------------------------------------------------------------

    def marca(self) -> float:
        """El reloj monótono de la fuente: lo que se pasa como `pedidas_en` a `recibir_velas`."""
        return self._monotono()

    def abierta(self) -> None:
        """El WebSocket acaba de abrir: hay que volver a pedirlo todo y rellenar los huecos."""
        with self._cerrojo:
            self._abierta = True
            self._desde = None
            self._por_rellenar |= self._series_seguidas
            for serie in self._series_seguidas:
                if serie in self._ultima:
                    self._rellenar_desde[serie] = self._ultima[serie]

    def cerrada(self, motivo: str) -> None:
        with self._cerrojo:
            if self._abierta or self._cerrada_en is None:
                self._cerrada_en = self._reloj()
            self._abierta = False
            self._desde = None
            self._motivo = motivo
            self._intentos += 1

    def recibir(self, mensaje: Mapping[str, Any]) -> None:
        """Un mensaje del WebSocket. Uno con forma rara se anota y se ignora: no tumba nada."""
        canal = mensaje.get("channel")
        datos = mensaje.get("data")
        ahora = self._monotono()
        with self._cerrojo:
            self._ultimo_mensaje = ahora
            if self._abierta and self._desde is None:
                self._desde = self._reloj()
                self._intentos = 0
                self._cerrada_en = None
        try:
            if canal == "allMids" and isinstance(datos, dict):
                self._poner_mids(leer_mids(cast("dict[str, Any]", datos)))
            elif canal == "l2Book" and isinstance(datos, dict):
                self._poner_libro(leer_libro(cast("dict[str, Any]", datos)))
            elif canal == "trades" and isinstance(datos, list):
                self._poner_operaciones(leer_operaciones(cast("list[Any]", datos)))
            elif canal == "candle" and isinstance(datos, dict):
                self._poner_velas([leer_vela(cast("dict[str, Any]", datos))], antes_de=ahora)
            elif canal == "error":
                log.warning("Hyperliquid dice: %s", str(datos)[:300])
        except (MensajeRaroError, KeyError, TypeError, ValueError) as error:
            log.warning("Mensaje de Hyperliquid (%s) que no se entiende: %s", canal, error)

    def recibir_mids(self, respuesta: Mapping[str, Any]) -> None:
        """`allMids` por REST (al arrancar, antes de que llegue el primero del WebSocket)."""
        self._poner_mids(leer_mids(respuesta))

    def recibir_meta(self, respuesta: Sequence[Any]) -> None:
        info = leer_meta(respuesta)
        with self._cerrojo:
            primera = not self._info
            self._info = info
            self._libros_seguidos &= set(info)
            self._series_seguidas = {s for s in self._series_seguidas if s[0] in info}
            self._por_rellenar = {s for s in self._por_rellenar if s[0] in info}
        if primera and self.al_seguir is not None:
            self.al_seguir()  # lo que se pidió antes de conocer la lista ya se puede suscribir

    def recibir_velas(
        self, coin: str, intervalo: str, respuesta: Sequence[Any], *, pedidas_en: float
    ) -> None:
        """Un `candleSnapshot`. No pisa las velas que el WebSocket actualizó después de pedirlo
        (`pedidas_en`, del mismo reloj monótono): esas son más recientes."""
        velas = [leer_vela(cast("dict[str, Any]", v)) for v in respuesta]
        velas = [v for v in velas if v.coin == coin and v.intervalo == intervalo]
        self._poner_velas(velas, antes_de=pedidas_en, desde_rest=True)
        with self._cerrojo:
            self._rellenando.discard((coin, intervalo))

    def rellenando(self, coin: str, intervalo: str) -> bool:
        """Si el histórico de esa serie se ha pedido y aún no ha llegado."""
        with self._cerrojo:
            serie = (coin, intervalo)
            return serie in self._por_rellenar or serie in self._rellenando

    def suscripciones(self) -> list[Suscripcion]:
        """Todo lo que tiene que estar pedido ahora: la lista de precios siempre; libros,
        operaciones y velas de lo seguido, solo si la moneda está en la lista de Hyperliquid."""
        with self._cerrojo:
            if not self._info and not self._mids:
                return [("allMids", "", "")]
            validas = self._info or self._mids
            pedidas: list[Suscripcion] = [("allMids", "", "")]
            for coin in sorted(self._libros_seguidos):
                if coin in validas:
                    pedidas.append(("l2Book", coin, ""))
                    pedidas.append(("trades", coin, ""))
            for coin, intervalo in sorted(self._series_seguidas):
                if coin in validas:
                    pedidas.append(("candle", coin, intervalo))
            return pedidas

    def por_rellenar(self) -> list[tuple[str, str, datetime]]:
        """Las series cuyo histórico hay que pedir por REST, con desde cuándo. Se dan una vez."""
        ahora = self._reloj()
        with self._cerrojo:
            validas = self._info or self._mids
            if not validas:
                return []
            listas = sorted(s for s in self._por_rellenar if s[0] in validas)
            self._por_rellenar -= set(listas)
            self._rellenando |= set(listas)
            pedidas: list[tuple[str, str, datetime]] = []
            for coin, intervalo in listas:
                # Tras un corte, desde la última vela que había al volver (no desde la que el
                # WebSocket haya traído ya, que dejaría el hueco sin tapar).
                ultima = self._rellenar_desde.pop((coin, intervalo), None)
                desde = (
                    hora(ultima)
                    if ultima is not None
                    else max(ahora - DURACION[intervalo] * MAX_VELAS, ANTES_DE_HYPERLIQUID)
                )
                pedidas.append((coin, intervalo, desde))
            return pedidas

    def volver_a_rellenar(self, coin: str, intervalo: str) -> None:
        """Un relleno que falló: se vuelve a intentar en la siguiente vuelta."""
        with self._cerrojo:
            self._rellenando.discard((coin, intervalo))
            if (coin, intervalo) in self._series_seguidas:
                self._por_rellenar.add((coin, intervalo))

    # -- Guardar ---------------------------------------------------------------------------------

    def _poner_mids(self, mids: dict[str, Decimal]) -> None:
        with self._cerrojo:
            self._mids = mids
            self._mids_at = self._reloj()
            self._mids_recibidos = self._monotono()

    def _poner_libro(self, libro: Libro) -> None:
        with self._cerrojo:
            self._libros[libro.coin] = libro
            self._libros_recibidos[libro.coin] = self._monotono()

    def _poner_operaciones(self, operaciones: list[Operacion]) -> None:
        with self._cerrojo:
            for operacion in operaciones:
                cola = self._operaciones.setdefault(
                    operacion.coin, deque[Operacion](maxlen=MAX_OPERACIONES)
                )
                cola.append(operacion)
                self._contador[operacion.coin] = self._contador.get(operacion.coin, 0) + 1

    def _poner_velas(self, velas: list[Vela], *, antes_de: float, desde_rest: bool = False) -> None:
        if not velas:
            return
        recibida = self._monotono()
        with self._cerrojo:
            for vela in velas:
                clave = (vela.coin, vela.intervalo)
                serie = self._series.setdefault(clave, {})
                t = ms(vela.inicio)
                previa = serie.get(t)
                if desde_rest and previa is not None and previa[1] > antes_de:
                    continue  # el WebSocket la actualizó después de pedir el histórico
                ultima = self._ultima.get(clave)
                # Solo la última puede seguir abierta: al empezar otra, la anterior se cierra.
                if ultima is not None and t < ultima:
                    serie[t] = (replace(vela, cerrada=True), recibida)
                    continue
                if ultima is not None and t > ultima and ultima in serie:
                    anterior, cuando = serie[ultima]
                    serie[ultima] = (replace(anterior, cerrada=True), cuando)
                serie[t] = (replace(vela, cerrada=False), recibida)
                self._ultima[clave] = t
                if len(serie) > MAX_VELAS + MAX_VELAS // 10:
                    for vieja in sorted(serie)[: len(serie) - MAX_VELAS]:
                        del serie[vieja]
