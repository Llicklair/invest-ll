"""El conector genérico sobre ccxt: el protocolo `Conector` para cualquier exchange con ficha.

**No importa ccxt.** Recibe el objeto de ccxt ya construido (`red_ccxt.construir`, el único módulo
del paquete que sale a la red) y lo usa a través de los métodos unificados de ccxt. Así se prueba
entero con un exchange falso, sin red, y los errores de ccxt se reconocen por el nombre de su clase,
como en `live/prueba_conexion.py`.

Lo que hace que una orden de un bot real sea segura, y dónde está:

- **Id de cliente** (`id_en_el_exchange`): cada exchange tiene su formato; el conector deriva uno
  válido, siempre el mismo para el mismo id. Antes de enviar se busca una orden con ese id: si ya
  existe (un reintento, aunque sea tras reiniciar el panel), se devuelve esa y **no se envía otra**.
- **Estado desconocido**: si la comunicación se corta al enviar (o el exchange acepta la orden pero
  no se puede leer cómo quedó), `EstadoDesconocidoError`. Nunca se adivina: se resuelve con
  `orden(par, id_cliente=...)`.
- **Redondeo y mínimos** (`_preparar`): la cantidad y el precio se redondean a los pasos del
  mercado con `amount_to_precision` / `price_to_precision` de ccxt (que saben las reglas raras,
  como las 5 cifras significativas de Hyperliquid) y, si no llega al mínimo, se dice en llano
  **antes** de enviar nada.
- **Comisión real** (`comision_de`): la que dice la orden; si no la trae, la de sus operaciones
  (`fetch_order_trades` o `fetch_my_trades`). Si se cobró en varias monedas, `None`: sumarlas sin
  convertir sería inventar.
- **Ninguna clave en ningún mensaje** (`limpiar`): los textos de error se filtran quitando los
  valores de las propias claves y cualquier texto que parezca llevar una.
"""

# Frontera con ccxt, que no publica tipos: lo que devuelve el exchange llega sin garantías. Se
# relaja solo aquí, como en live/ccxt_broker.py.
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import hashlib
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from invest_ll.exchanges.conector import (
    EstadoDesconocidoError,
    EstadoOrdenExchange,
    ExchangeError,
    Lado,
    Mercado,
    OrdenExchange,
    Permisos,
    Red,
)
from invest_ll.vivo.fuente import Libro, Nivel, Vela

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable, Iterable, Mapping

    from invest_ll.exchanges.fichas import Ficha, FormatoId

TIPO_CCXT: Final[dict[str, str]] = {"mercado": "market", "limite": "limit"}
LADO_CCXT: Final[dict[str, str]] = {"compra": "buy", "venta": "sell"}
RECARGAR_MERCADOS: Final = timedelta(hours=1)
VENTANA_RECIENTES: Final = timedelta(days=7)
"""Hasta dónde se mira, en los exchanges que no buscan por id de cliente (Coinbase)."""
REPASOS_TRAS_ENVIAR: Final = 3
ESPERA_REPASO: Final = 0.5
LONGITUD_MAXIMA_ERROR: Final = 200
TICK_SIZE: Final = 4
"""`ccxt.TICK_SIZE`: la precisión es el paso (0.001), no el número de decimales (3)."""

MARCAS_DE_CLAVE: Final = (
    "apikey",
    "api_key",
    "secret",
    "signature",
    "authorization",
    "privatekey",
    "private key",
    "password",
    "passphrase",
)

FORMATOS_ID: Final[dict[FormatoId, re.Pattern[str]]] = {
    # Binance (`^[.A-Z:/a-z0-9_-]{1,36}$`) y Bybit (36, letras, números, - y _): lo común a los dos.
    "texto36": re.compile(r"[A-Za-z0-9_-]{1,36}"),
    # OKX: letras y números, hasta 32.
    "alnum32": re.compile(r"[A-Za-z0-9]{1,32}"),
    # Kraken (`cl_ord_id`): un UUID con o sin guiones, o texto libre de hasta 18.
    "kraken": re.compile(
        r"[A-Za-z0-9_-]{1,18}|[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    ),
    # Coinbase: cualquier texto; se acota para que sea legible.
    "texto64": re.compile(r"[A-Za-z0-9_-]{1,64}"),
    # Hyperliquid (`cloid`): 128 bits en hexadecimal.
    "hex128": re.compile(r"0x[0-9a-f]{32}"),
}


# -- Lo que no depende del exchange: ids, números, errores ----------------------------------------


def id_en_el_exchange(formato: FormatoId, id_cliente: str) -> str:
    """El id de cliente que ve el exchange: el mismo si ya vale; si no, uno derivado de él.

    Siempre el mismo para el mismo `id_cliente` (es lo que hace que un reintento no duplique) y
    distinto para ids distintos (salvo una colisión de SHA-256, que no va a pasar).
    """
    if not id_cliente.strip():
        raise ExchangeError("Una orden necesita un id de cliente: sin él, un reintento la duplica.")
    if FORMATOS_ID[formato].fullmatch(id_cliente):
        return id_cliente
    huella = hashlib.sha256(f"invest-ll:{id_cliente}".encode()).hexdigest()
    derivados: dict[FormatoId, str] = {
        "texto36": "il" + huella[:30],
        "alnum32": "il" + huella[:30],
        "kraken": huella[:32],
        "texto64": "il-" + huella[:40],
        "hex128": "0x" + huella[:32],
    }
    return derivados[formato]


def decimal(valor: object) -> Decimal | None:
    """Un número de ccxt como Decimal (pasando por `str`), o `None` si no es un número."""
    if valor is None or isinstance(valor, bool) or valor == "":
        return None
    try:
        numero = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero.is_finite() else None


def tipos_de(error: BaseException) -> set[str]:
    """Los nombres de la clase del error y de sus padres (se reconocen sin importar ccxt)."""
    return {t.__name__ for t in type(error).__mro__}


def es_incierto(error: BaseException) -> bool:
    """Si tras este error NO se sabe si el exchange hizo lo pedido.

    En ccxt, `OperationFailed` agrupa lo que puede haber llegado o no: la red, un tiempo agotado,
    el exchange caído, una respuesta ilegible. `InvalidNonce` también cuelga de ahí, pero es un
    rechazo (la hora). Y un error que no es de ccxt no dice dónde se rompió: también incierto.
    """
    tipos = tipos_de(error)
    if "InvalidNonce" in tipos:
        return False
    if "OperationFailed" in tipos:
        return True
    return "BaseError" not in tipos


def limpiar(texto: str, valores: Iterable[str] = ()) -> str:
    """El texto de un error sin nada que pueda ser una clave: fuera los valores de las claves y,
    si aun así parece llevar una, el mensaje entero. Recortado."""
    for valor in valores:
        if len(valor) >= 6:
            texto = texto.replace(valor, "***")
    minusculas = texto.lower()
    for marca in MARCAS_DE_CLAVE:
        if marca in minusculas:
            return f"mensaje del exchange omitido (contenía «{marca}»)"
    return texto[:LONGITUD_MAXIMA_ERROR]


# -- De ccxt a nuestros tipos ----------------------------------------------------------------------


def _dict(valor: object) -> dict[str, Any]:
    return cast("dict[str, Any]", valor) if isinstance(valor, dict) else {}


def _lista(valor: object) -> list[Any]:
    return cast("list[Any]", valor) if isinstance(valor, list) else []


def _paso(valor: object, modo: object) -> Decimal | None:
    numero = decimal(valor)
    if numero is None:
        return None
    if modo == TICK_SIZE:
        return numero
    return Decimal(1).scaleb(-int(numero))  # precisión en decimales: 3 -> 0.001


def mercado_de(m: Mapping[str, Any], modo_precision: object = TICK_SIZE) -> Mercado:
    limites = _dict(m.get("limits"))
    precision = _dict(m.get("precision"))
    return Mercado(
        par=str(m["symbol"]),
        base=str(m.get("base") or ""),
        cotizada=str(m.get("quote") or ""),
        minimo_importe=decimal(_dict(limites.get("cost")).get("min")),
        minimo_cantidad=decimal(_dict(limites.get("amount")).get("min")),
        paso_cantidad=_paso(precision.get("amount"), modo_precision),
        paso_precio=_paso(precision.get("price"), modo_precision),
        comision_tomador=decimal(m.get("taker")),
        comision_creador=decimal(m.get("maker")),
    )


def es_contado(m: Mapping[str, Any]) -> bool:
    return bool(m.get("spot")) and m.get("active") is not False


def estado_de(crudo: Mapping[str, Any]) -> EstadoOrdenExchange:
    """El estado de una orden de ccxt en nuestras palabras."""
    estado = str(crudo.get("status") or "").lower()
    ejecutada = decimal(crudo.get("filled")) or Decimal(0)
    pedida = decimal(crudo.get("amount"))
    if estado == "open":
        return "parcial" if ejecutada > 0 else "abierta"
    if estado == "closed":
        if ejecutada <= 0:
            return "cancelada"
        if pedida is not None and ejecutada < pedida:
            return "parcial"
        return "ejecutada"
    if estado in ("canceled", "cancelled", "expired"):
        return "parcial" if ejecutada > 0 else "cancelada"
    if estado == "rejected":
        return "rechazada"
    return "desconocido"


def comision_de(crudo: Mapping[str, Any]) -> tuple[Decimal | None, str | None]:
    """Lo que cobró el exchange y en qué moneda, si lo dice. `(None, None)` si no.

    Como `live.ccxt_broker.comision_declarada` (que ya resolvió el lío de Binance: la comisión de
    una orden de mercado viene repartida en sus `fills`), pero sabiendo la moneda: si se cobró en
    varias, no se suman.
    """
    trozos: list[tuple[Decimal, str | None]] = []
    fee = _dict(crudo.get("fee"))
    if fee.get("cost") is not None:
        trozos = _trozos([fee], "cost", "currency")
    if not trozos:
        trozos = _trozos(_lista(crudo.get("fees")), "cost", "currency")
    if not trozos:
        trozos = _trozos(
            [_dict(t).get("fee") for t in _lista(crudo.get("trades"))], "cost", "currency"
        )
    if not trozos:
        info = _dict(crudo.get("info"))
        trozos = _trozos(_lista(info.get("fills")), "commission", "commissionAsset")
    if not trozos:
        return None, None
    con_coste = [(c, m) for c, m in trozos if c != 0] or trozos
    monedas = {m for _, m in con_coste}
    if len(monedas) != 1:
        return None, None
    return sum((c for c, _ in con_coste), Decimal(0)), next(iter(monedas))


def _trozos(lista: list[Any], campo: str, campo_moneda: str) -> list[tuple[Decimal, str | None]]:
    salida: list[tuple[Decimal, str | None]] = []
    for trozo in lista:
        d = _dict(trozo)
        coste = decimal(d.get(campo))
        if coste is None:
            continue
        moneda = d.get(campo_moneda)
        salida.append((abs(coste), str(moneda) if moneda else None))
    return salida


def _momento(ms: object) -> datetime | None:
    numero = decimal(ms)
    if numero is None or numero <= 0:
        return None
    return datetime.fromtimestamp(float(numero) / 1000, tz=UTC)


def _ms(momento: datetime) -> int:
    return int(momento.timestamp() * 1000)


def fin_de_vela(inicio: datetime, intervalo: str) -> datetime:
    """Cuándo acaba una vela de ese intervalo ('1m', '4h', '1d', '1w', '1M'...)."""
    cantidad = int(intervalo[:-1] or 1)
    unidad = intervalo[-1]
    if unidad == "M":
        meses = inicio.month - 1 + cantidad
        return inicio.replace(year=inicio.year + meses // 12, month=meses % 12 + 1)
    segundos = {"s": 1, "m": 60, "h": 3600, "d": 86_400, "w": 604_800}[unidad]
    return inicio + timedelta(seconds=segundos * cantidad)


def vela_de(fila: list[Any], par: str, intervalo: str, ahora: datetime) -> Vela | None:
    """Una fila OHLCV de ccxt `[ms, apertura, máximo, mínimo, cierre, volumen]`."""
    if len(fila) < 5:
        return None
    inicio = _momento(fila[0])
    precios = [decimal(v) for v in fila[1:5]]
    if inicio is None or any(p is None for p in precios):
        return None
    apertura, maximo, minimo, cierre = cast("list[Decimal]", precios)
    fin = fin_de_vela(inicio, intervalo)
    return Vela(
        coin=par,
        intervalo=intervalo,
        inicio=inicio,
        fin=fin,
        apertura=apertura,
        maximo=maximo,
        minimo=minimo,
        cierre=cierre,
        volumen=decimal(fila[5] if len(fila) > 5 else None) or Decimal(0),
        cerrada=fin <= ahora,
    )


# -- Los permisos de una clave, exchange a exchange -------------------------------------------------

PUEDE_RETIRAR: Final = "¡La clave PUEDE RETIRAR fondos! Crea otra sin ese permiso: con esta no se activa el dinero real."


def _texto_permisos(operar: bool | None, retirar: bool | None) -> str:
    if retirar:
        return PUEDE_RETIRAR
    partes = [
        "puede operar en contado"
        if operar
        else "NO puede operar en contado"
        if operar is False
        else "no se sabe si puede operar"
    ]
    partes.append("no puede retirar" if retirar is False else "no se sabe si puede retirar")
    texto = " y ".join(partes)
    return texto[0].upper() + texto[1:] + "."


def permisos_binance(crudo: Mapping[str, Any]) -> Permisos:
    """`GET /sapi/v1/account/apiRestrictions`."""
    retirar = crudo.get("enableWithdrawals")
    operar = crudo.get("enableSpotAndMarginTrading")
    r = bool(retirar) if retirar is not None else None
    o = bool(operar) if operar is not None else None
    return Permisos(operar=o, retirar=r, texto=_texto_permisos(o, r))


def permisos_bybit(crudo: Mapping[str, Any]) -> Permisos:
    """`GET /v5/user/query-api`: `readOnly` (1 = solo lectura) y `permissions` por grupo."""
    resultado = _dict(crudo.get("result")) or _dict(crudo)
    permisos = _dict(resultado.get("permissions"))
    if not permisos:
        return Permisos(None, None, "Bybit no dijo los permisos de la clave.")
    solo_lectura = str(resultado.get("readOnly", "")) == "1"
    retirar = "Withdraw" in _lista(permisos.get("Wallet"))
    operar = not solo_lectura and "SpotTrade" in _lista(permisos.get("Spot"))
    return Permisos(operar=operar, retirar=retirar, texto=_texto_permisos(operar, retirar))


def permisos_okx(crudo: Mapping[str, Any]) -> Permisos:
    """`GET /api/v5/account/config`: `perm` es 'read_only', 'trade' y/o 'withdraw', con comas."""
    datos = _lista(crudo.get("data"))
    perm = _dict(datos[0]).get("perm") if datos else None
    if not isinstance(perm, str):
        return Permisos(None, None, "OKX no dijo los permisos de la clave.")
    lista = {p.strip() for p in perm.split(",")}
    retirar = "withdraw" in lista
    operar = "trade" in lista
    return Permisos(operar=operar, retirar=retirar, texto=_texto_permisos(operar, retirar))


def permisos_kraken(crudo: Mapping[str, Any]) -> Permisos:
    """`POST /0/private/GetApiKeyInfo`: `permissions`, una lista ('withdraw-funds', ...)."""
    resultado = _dict(crudo.get("result")) or _dict(crudo)
    lista = _lista(resultado.get("permissions"))
    if not lista:
        return Permisos(None, None, "Kraken no dijo los permisos de la clave.")
    retirar = "withdraw-funds" in lista
    operar = "modify-trades" in lista
    return Permisos(operar=operar, retirar=retirar, texto=_texto_permisos(operar, retirar))


def permisos_coinbase(crudo: Mapping[str, Any]) -> Permisos:
    """`GET /api/v3/brokerage/key_permissions`: `can_trade` y `can_transfer` (depositar/retirar)."""
    if "can_transfer" not in crudo:
        return Permisos(None, None, "Coinbase no dijo los permisos de la clave.")
    retirar = bool(crudo.get("can_transfer"))
    operar = bool(crudo.get("can_trade"))
    return Permisos(operar=operar, retirar=retirar, texto=_texto_permisos(operar, retirar))


def permisos_hyperliquid(cartera: str, firmante: str, agentes: list[Any] | None) -> Permisos:
    """Una API wallet no puede retirar; la clave privada de la cartera principal, sí.

    `firmante` es la dirección que sale de la clave privada; `agentes`, las API wallets aprobadas
    para la cartera (`extraAgents`), o `None` si no se pudieron leer.
    """
    if firmante.lower() == cartera.lower():
        return Permisos(
            operar=True,
            retirar=True,
            texto=(
                "Es la clave privada de tu cartera principal: PUEDE RETIRAR. Crea una API wallet "
                "(More → API) y pega su clave privada: con esta no se activa el dinero real."
            ),
        )
    if agentes is None:
        return Permisos(
            operar=None,
            retirar=False,
            texto="Es una API wallet (no puede retirar); no se pudo comprobar si está aprobada.",
        )
    aprobadas = {str(_dict(a).get("address", "")).lower() for a in agentes}
    if firmante.lower() in aprobadas:
        return Permisos(
            operar=True,
            retirar=False,
            texto="Es una API wallet aprobada para tu cartera: puede operar y no puede retirar.",
        )
    return Permisos(
        operar=False,
        retirar=False,
        texto=(
            "Esa API wallet no está aprobada para esta cartera (o caducó): autorízala en "
            "Hyperliquid (More → API) o revisa la dirección de la cartera."
        ),
    )


# -- El conector -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Preparada:
    """Una orden lista para enviar: redondeada y comprobada contra los mínimos."""

    cantidad: str
    precio: str | None
    precio_de_referencia: Decimal | None


class ConectorCcxt:
    """Un exchange de ccxt en una red. Sin claves (`claves=None`) solo da datos públicos.

    `ex` es el objeto de ccxt (o un doble en las pruebas). `dormir` solo se cambia en las pruebas.
    Las llamadas pasan de una en una (`_cerrojo`): los objetos de ccxt no están pensados para
    usarse desde varios hilos a la vez, y las rutas del panel corren en varios.
    """

    def __init__(
        self,
        ex: Any,
        ficha: Ficha,
        red: Red,
        *,
        claves: Mapping[str, str] | None = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ex = ex
        self._ficha = ficha
        self._red: Red = red
        self._valores = tuple(v for v in (claves or {}).values() if v)
        self._con_claves = claves is not None
        self._dormir = dormir
        self._reloj = reloj
        self._cerrojo = threading.RLock()
        self._cargados: datetime | None = None
        self._ids: dict[str, str] = {}
        """Id en el exchange -> id de quien envió, para devolver el suyo en `ordenes_abiertas`."""

    @property
    def exchange(self) -> str:
        return self._ficha.id

    @property
    def red(self) -> Red:
        return self._red

    @property
    def ficha(self) -> Ficha:
        return self._ficha

    # -- llamar a ccxt -------------------------------------------------------------------------

    def _limpiar(self, error: BaseException) -> str:
        return limpiar(str(error), self._valores)

    def explicar(self, error: BaseException, que: str) -> str:
        """Qué ha pasado, en llano, según el tipo de error de ccxt."""
        tipos = tipos_de(error)
        nombre = self._ficha.nombre
        red = "la red de pruebas" if self._red == "pruebas" else "dinero real"
        if "InvalidNonce" in tipos:
            return (
                f"{nombre} rechaza la petición ({que}) porque la hora de tu ordenador no coincide "
                "con la suya: sincroniza el reloj de Windows y vuelve a probar."
            )
        if "AccountSuspended" in tipos:
            return f"{nombre} dice que la cuenta está suspendida ({que})."
        if "AuthenticationError" in tipos:
            return (
                f"{nombre} rechaza las claves ({que}). Revisa que estén copiadas enteras y sin "
                f"espacios, que sean de {red} (las de pruebas no valen en real ni al revés) y que "
                "tengan permiso de lectura y de contado; si la clave tiene restringida la IP, que "
                "sea la tuya."
            )
        if "RestrictedLocation" in tipos:
            return f"{nombre} no deja hacer esto desde tu país ({que})."
        if "InsufficientFunds" in tipos:
            return f"No hay saldo suficiente en {nombre} para esta orden."
        if "BadSymbol" in tipos:
            return f"{nombre} no tiene ese par de contado ({que})."
        if "OperationFailed" in tipos:
            return (
                f"No hay conexión con {nombre} ({que}): revisa tu conexión a internet y vuelve a "
                "probar. Si es la red de pruebas, a veces está caída."
            )
        if "InvalidOrder" in tipos:
            return f"{nombre} no acepta la orden: {self._limpiar(error)}"
        return f"{nombre} dijo que no ({que}): {type(error).__name__}: {self._limpiar(error)}"

    def _leer[T](self, que: str, funcion: Callable[[], T]) -> T:
        """Una llamada que no cambia nada en el exchange: si falla, `ExchangeError` en llano."""
        with self._cerrojo:
            try:
                return funcion()
            except ExchangeError:
                raise
            except Exception as error:
                raise ExchangeError(self.explicar(error, que)) from None

    def _exigir_claves(self) -> None:
        if not self._con_claves:
            raise ExchangeError(
                f"Este conector de {self._ficha.nombre} no tiene claves: solo da datos públicos."
            )

    # -- mercados ------------------------------------------------------------------------------

    def _mercados_ccxt(self) -> dict[str, Any]:
        with self._cerrojo:
            ahora = self._reloj()
            if self._cargados is None or ahora - self._cargados > RECARGAR_MERCADOS:
                recargar = self._cargados is not None
                self._leer("leer sus mercados", lambda: self._ex.load_markets(recargar))
                self._cargados = ahora
            return _dict(self._ex.markets)

    def _mercado_ccxt(self, par: str) -> dict[str, Any]:
        m = _dict(self._mercados_ccxt().get(par))
        if not m or not es_contado(m):
            raise ExchangeError(
                f"{self._ficha.nombre} no tiene el par {par} de contado (o no está activo)."
            )
        return m

    def mercados(self) -> list[Mercado]:
        modo = getattr(self._ex, "precisionMode", TICK_SIZE)
        return sorted(
            (
                mercado_de(_dict(m), modo)
                for m in self._mercados_ccxt().values()
                if es_contado(_dict(m))
            ),
            key=lambda m: m.par,
        )

    def mercado(self, par: str) -> Mercado:
        return mercado_de(self._mercado_ccxt(par), getattr(self._ex, "precisionMode", TICK_SIZE))

    def precio(self, par: str) -> Decimal | None:
        self._mercado_ccxt(par)
        ticker = _dict(self._leer(f"leer el precio de {par}", lambda: self._ex.fetch_ticker(par)))
        for campo in ("last", "close"):
            valor = decimal(ticker.get(campo))
            if valor is not None and valor > 0:
                return valor
        compra, venta = decimal(ticker.get("bid")), decimal(ticker.get("ask"))
        if compra is not None and venta is not None:
            return (compra + venta) / 2
        return None

    def libro(self, par: str, niveles: int = 20) -> Libro | None:
        self._mercado_ccxt(par)
        niveles = max(1, niveles)
        pedir = self._tamano_libro(niveles)
        crudo = _dict(
            self._leer(f"leer el libro de {par}", lambda: self._ex.fetch_order_book(par, pedir))
        )
        if not crudo:
            return None
        return Libro(
            coin=par,
            compras=_niveles(crudo.get("bids"), niveles),
            ventas=_niveles(crudo.get("asks"), niveles),
            at=_momento(crudo.get("timestamp")) or self._reloj(),
        )

    def _tamano_libro(self, niveles: int) -> int | None:
        if self._ficha.tamanos_libro is not None:
            return next((t for t in self._ficha.tamanos_libro if t >= niveles), None)
        return min(niveles, self._ficha.max_libro)

    def velas(
        self, par: str, intervalo: str, desde: datetime | None = None, limite: int = 1000
    ) -> list[Vela]:
        self._mercado_ccxt(par)
        disponibles = list(_dict(getattr(self._ex, "timeframes", None) or {}))
        if disponibles and intervalo not in disponibles:
            raise ExchangeError(
                f"{self._ficha.nombre} no tiene velas de {intervalo}: tiene "
                f"{', '.join(disponibles)}."
            )
        limite = max(1, limite)
        ahora = self._reloj()
        por_peticion = self._ficha.max_velas
        if desde is None:
            if limite <= por_peticion:
                return self._pedir_velas(par, intervalo, None, limite, ahora)[-limite:]
            desde = ahora - (fin_de_vela(ahora, intervalo) - ahora) * limite
        salida: list[Vela] = []
        cursor = desde
        for _ in range(limite // por_peticion + 5):
            if len(salida) >= limite or cursor > ahora:
                break
            pedir = min(por_peticion, limite - len(salida))
            nuevas = [
                v
                for v in self._pedir_velas(par, intervalo, cursor, pedir, ahora)
                if not salida or v.inicio > salida[-1].inicio
            ]
            if not nuevas:
                break
            salida.extend(nuevas)
            cursor = nuevas[-1].fin
        return salida[:limite]

    def _pedir_velas(
        self, par: str, intervalo: str, desde: datetime | None, limite: int, ahora: datetime
    ) -> list[Vela]:
        since = _ms(desde) if desde is not None else None
        filas = self._leer(
            f"leer las velas de {par}",
            lambda: self._ex.fetch_ohlcv(par, intervalo, since, limite),
        )
        velas = (vela_de(_lista(f), par, intervalo, ahora) for f in _lista(filas))
        return sorted((v for v in velas if v is not None), key=lambda v: v.inicio)

    # -- cuenta --------------------------------------------------------------------------------

    def saldo(self) -> dict[str, Decimal]:
        self._exigir_claves()
        params = dict(self._ficha.params_saldo)
        crudo = _dict(self._leer("leer el saldo", lambda: self._ex.fetch_balance(params)))
        libres = _dict(crudo.get("free"))
        salida: dict[str, Decimal] = {}
        for moneda, cantidad in libres.items():
            valor = decimal(cantidad)
            if valor is not None and valor > 0:
                salida[str(moneda)] = valor
        return salida

    def permisos(self) -> Permisos:
        """Lo que se sabe de la clave. Si no se puede leer, `None` en lo que no se sabe y el
        motivo en el texto: no se adivina."""
        self._exigir_claves()
        como = self._ficha.permisos
        try:
            if como == "binance":
                if self._red == "pruebas":
                    return Permisos(
                        None,
                        None,
                        "La red de pruebas de Binance no dice los permisos de la clave (en dinero "
                        "real sí se comprueba).",
                    )
                return permisos_binance(_dict(self._llamada("sapiGetAccountApiRestrictions")))
            if como == "bybit":
                return permisos_bybit(_dict(self._llamada("privateGetV5UserQueryApi")))
            if como == "okx":
                return permisos_okx(_dict(self._llamada("privateGetAccountConfig")))
            if como == "kraken":
                return permisos_kraken(_dict(self._llamada("privatePostGetApiKeyInfo")))
            if como == "coinbase":
                return permisos_coinbase(
                    _dict(self._llamada("v3PrivateGetBrokerageKeyPermissions"))
                )
            return self._permisos_hyperliquid()
        except ExchangeError as error:
            return Permisos(None, None, f"No se pudieron leer los permisos de la clave: {error}")

    def _llamada(self, metodo: str, params: Mapping[str, Any] | None = None) -> Any:
        """Un método de la API propia del exchange (los "implícitos" de ccxt), por su nombre."""
        funcion = getattr(self._ex, metodo, None)
        if funcion is None:
            raise ExchangeError(f"ccxt ya no tiene {metodo} para {self._ficha.nombre}.")
        return self._leer("leer los permisos de la clave", lambda: funcion(dict(params or {})))

    def _permisos_hyperliquid(self) -> Permisos:
        cartera = self._valor("walletAddress")
        clave = self._valor("privateKey")
        try:
            firmante = str(self._ex.eth_get_address_from_private_key(clave))
        except Exception:
            return Permisos(
                False,
                None,
                "La clave privada no tiene el formato de una clave de Hyperliquid (0x y 64 "
                "caracteres hexadecimales).",
            )
        try:
            agentes = _lista(
                self._llamada("publicPostInfo", {"type": "extraAgents", "user": cartera})
            )
        except ExchangeError:
            return permisos_hyperliquid(cartera, firmante, None)
        return permisos_hyperliquid(cartera, firmante, agentes)

    def _valor(self, campo: str) -> str:
        return str(getattr(self._ex, campo, "") or "")

    # -- órdenes -------------------------------------------------------------------------------

    def enviar(
        self,
        par: str,
        lado: Lado,
        cantidad: Decimal,
        *,
        id_cliente: str,
        tipo: Literal["mercado", "limite"] = "mercado",
        precio: Decimal | None = None,
    ) -> OrdenExchange:
        self._exigir_claves()
        if lado not in LADO_CCXT or tipo not in TIPO_CCXT:
            raise ExchangeError(f"Orden no válida: lado {lado!r}, tipo {tipo!r}.")
        if tipo == "limite" and (precio is None or precio <= 0):
            raise ExchangeError("Una orden límite necesita un precio mayor que cero.")
        mercado = self._mercado_ccxt(par)
        id_ex = id_en_el_exchange(self._ficha.formato_id, id_cliente)
        with self._cerrojo:
            self._ids[id_ex] = id_cliente
            # 1. Un reintento no duplica: si ya hay una orden con este id, es esa.
            previa = self._buscar_o_fallar(
                par, id_ex, "comprobar si esa orden ya existía (no se ha enviado nada)"
            )
            if previa is not None:
                self._exigir_la_misma(previa, par, lado, id_cliente)
                return self._orden(previa, id_cliente, par, lado, tipo, cantidad)
            # 2. Redondear y comprobar los mínimos ANTES de enviar.
            lista = self._preparar(mercado, par, lado, cantidad, tipo, precio)
            # 3. Enviar.
            crudo = self._crear(par, lado, tipo, lista, id_ex, id_cliente)
            # 4. Lo que la respuesta no trae (estado, ejecutado, comisión).
            try:
                crudo = self._completar(par, id_ex, crudo, tipo)
            except Exception:
                raise EstadoDesconocidoError(
                    f"{self._ficha.nombre} aceptó la orden {id_cliente} pero no se pudo leer cómo "
                    "quedó: NO se sabe cuánto se ejecutó. Consúltala antes de seguir."
                ) from None
            return self._orden(crudo, id_cliente, par, lado, tipo, Decimal(lista.cantidad))

    def _preparar(
        self,
        mercado: Mapping[str, Any],
        par: str,
        lado: Lado,
        cantidad: Decimal,
        tipo: Literal["mercado", "limite"],
        precio: Decimal | None,
    ) -> Preparada:
        m = mercado_de(mercado, getattr(self._ex, "precisionMode", TICK_SIZE))
        if cantidad <= 0:
            raise ExchangeError(f"La cantidad tiene que ser mayor que cero (pediste {cantidad}).")
        try:
            redondeada = str(self._ex.amount_to_precision(par, str(cantidad)))
            precio_txt = (
                str(self._ex.price_to_precision(par, str(precio)))
                if tipo == "limite" and precio is not None
                else None
            )
        except Exception:
            redondeada, precio_txt = "0", None
        cant = decimal(redondeada) or Decimal(0)
        paso = f" (paso {_txt(m.paso_cantidad)})" if m.paso_cantidad is not None else ""
        if cant <= 0:
            raise ExchangeError(
                f"La cantidad {_txt(cantidad)} {m.base} se queda en cero al redondearla al paso "
                f"de {par} en {self._ficha.nombre}{paso}."
            )
        if m.minimo_cantidad is not None and cant < m.minimo_cantidad:
            raise ExchangeError(
                f"La cantidad mínima de {par} en {self._ficha.nombre} es "
                f"{_txt(m.minimo_cantidad)} {m.base}; esta orden son {_txt(cant)}{paso}."
            )
        referencia = (decimal(precio_txt) if precio_txt is not None else None) or self.precio(par)
        if m.minimo_importe is not None:
            if referencia is None:
                raise ExchangeError(
                    f"No se pudo leer el precio de {par} para comprobar el importe mínimo: no se "
                    "ha enviado nada."
                )
            importe = cant * referencia
            if importe < m.minimo_importe:
                raise ExchangeError(
                    f"El importe mínimo de una orden de {par} en {self._ficha.nombre} es "
                    f"{_txt(m.minimo_importe)} {m.cotizada}; esta son unos "
                    f"{format(importe.quantize(Decimal('0.01')), 'f')} {m.cotizada}."
                )
        if tipo == "mercado" and self._ficha.compra_a_mercado_con_precio and referencia is None:
            raise ExchangeError(
                f"{self._ficha.nombre} necesita el precio para una orden a mercado y no se pudo "
                "leer: no se ha enviado nada."
            )
        return Preparada(cantidad=redondeada, precio=precio_txt, precio_de_referencia=referencia)

    def _crear(
        self,
        par: str,
        lado: Lado,
        tipo: Literal["mercado", "limite"],
        lista: Preparada,
        id_ex: str,
        id_cliente: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            **dict(self._ficha.params_orden),
            self._ficha.param_id_cliente: id_ex,
        }
        if tipo == "limite":
            precio = float(lista.precio) if lista.precio is not None else None
        elif self._ficha.compra_a_mercado_con_precio and lista.precio_de_referencia is not None:
            precio = float(lista.precio_de_referencia)
        else:
            precio = None
        try:
            return _dict(
                self._ex.create_order(
                    par,
                    TIPO_CCXT[tipo],
                    LADO_CCXT[lado],
                    float(lista.cantidad),
                    precio,
                    params,
                )
            )
        except Exception as error:
            if "DuplicateOrderId" in tipos_de(error):
                # El exchange ya tiene una orden con este id: es la de un intento anterior.
                existente = self._buscar_o_none(par, id_ex)
                if existente is not None:
                    return existente
            if es_incierto(error):
                raise EstadoDesconocidoError(
                    f"Se envió la orden {id_cliente} a {self._ficha.nombre} y se cortó la "
                    f"comunicación ({type(error).__name__}): NO se sabe si se ejecutó. "
                    "Consúltala con su id de cliente antes de nada."
                ) from None
            raise ExchangeError(self.explicar(error, "enviar la orden")) from None

    def _completar(
        self, par: str, id_ex: str, crudo: dict[str, Any], tipo: Literal["mercado", "limite"]
    ) -> dict[str, Any]:
        """La respuesta de crear una orden trae poco en muchos exchanges (OKX, Bybit, Kraken y
        Coinbase, solo los ids): se lee la orden. Una de mercado aún abierta se vuelve a leer unas
        pocas veces. Y si no trae la comisión, se buscan sus operaciones."""
        actual = crudo
        for intento in range(REPASOS_TRAS_ENVIAR + 1):
            falta = actual.get("status") is None or actual.get("filled") is None
            abierta = tipo == "mercado" and estado_de(actual) in ("abierta", "parcial")
            if not falta and not abierta:
                break
            if intento:
                self._dormir(ESPERA_REPASO)
            leida = self._buscar(par, id_ex)
            if leida is not None:
                actual = {**actual, **{k: v for k, v in leida.items() if v is not None}}
        if actual.get("status") is None or actual.get("filled") is None:
            raise ExchangeError("no se pudo leer la orden recién enviada")
        return self._con_comision(par, actual)

    def _con_comision(self, par: str, crudo: dict[str, Any]) -> dict[str, Any]:
        comision, _ = comision_de(crudo)
        ejecutada = decimal(crudo.get("filled")) or Decimal(0)
        if comision is not None or ejecutada <= 0 or not crudo.get("id"):
            return crudo
        operaciones = self._operaciones_de(par, crudo)
        return {**crudo, "trades": operaciones} if operaciones else crudo

    def _operaciones_de(self, par: str, crudo: Mapping[str, Any]) -> list[Any]:
        """Las operaciones (fills) de una orden, para saber su comisión. Vacío si no se puede."""
        id_orden = str(crudo.get("id"))
        has = _dict(getattr(self._ex, "has", None))
        try:
            if has.get("fetchOrderTrades"):
                return _lista(self._ex.fetch_order_trades(id_orden, par))
            if has.get("fetchMyTrades"):
                cuando = _momento(crudo.get("timestamp")) or self._reloj()
                desde = _ms(cuando - timedelta(minutes=1))
                return [
                    t
                    for t in _lista(self._ex.fetch_my_trades(par, desde))
                    if str(_dict(t).get("order")) == id_orden
                ]
        except Exception:
            return []
        return []

    def _buscar(self, par: str, id_ex: str) -> dict[str, Any] | None:
        """La orden con ese id de cliente, o `None` si el exchange no la tiene. Lanza lo que lance
        ccxt si no se puede preguntar."""
        f = self._ficha
        filtro = {f.param_buscar_id: id_ex}
        if f.buscar_por_id == "fetch_order":
            try:
                orden = _dict(self._ex.fetch_order("", par, filtro))
            except Exception as error:
                if "OrderNotFound" in tipos_de(error):
                    return None
                raise
            return orden if orden.get("id") else None
        if f.buscar_por_id == "abiertas_y_cerradas":
            abiertas = _lista(self._ex.fetch_open_orders(par, None, None, filtro))
            encontrada = _con_id(abiertas, id_ex)
            if encontrada is not None:
                return encontrada
            has = _dict(getattr(self._ex, "has", None))
            if has.get("fetchCanceledAndClosedOrders"):
                cerradas = self._ex.fetch_canceled_and_closed_orders(par, None, None, filtro)
            else:
                cerradas = self._ex.fetch_closed_orders(par, None, None, filtro)
            return _con_id(_lista(cerradas), id_ex)
        desde = _ms(self._reloj() - VENTANA_RECIENTES)
        return _con_id(_lista(self._ex.fetch_orders(par, desde, 100)), id_ex)

    def _buscar_o_fallar(self, par: str, id_ex: str, que: str) -> dict[str, Any] | None:
        try:
            return self._buscar(par, id_ex)
        except Exception as error:
            raise ExchangeError(self.explicar(error, que)) from None

    def _buscar_o_none(self, par: str, id_ex: str) -> dict[str, Any] | None:
        try:
            return self._buscar(par, id_ex)
        except Exception:
            return None

    def _exigir_la_misma(
        self, previa: Mapping[str, Any], par: str, lado: Lado, id_cliente: str
    ) -> None:
        simbolo = previa.get("symbol")
        lado_previo = previa.get("side")
        if (simbolo is not None and simbolo != par) or (
            lado_previo is not None and lado_previo != LADO_CCXT[lado]
        ):
            raise ExchangeError(
                f"El id de cliente {id_cliente} ya se usó en {self._ficha.nombre} para otra orden "
                f"({lado_previo} {simbolo}): cada orden necesita el suyo."
            )

    def _orden(
        self,
        crudo: Mapping[str, Any],
        id_cliente: str,
        par: str,
        lado: Lado,
        tipo: Literal["mercado", "limite"],
        cantidad: Decimal,
    ) -> OrdenExchange:
        ejecutada = decimal(crudo.get("filled")) or Decimal(0)
        medio = decimal(crudo.get("average"))
        if medio is None and ejecutada > 0:
            coste = decimal(crudo.get("cost"))
            medio = coste / ejecutada if coste else decimal(crudo.get("price"))
        comision, moneda = comision_de(crudo)
        id_exchange = crudo.get("id")
        return OrdenExchange(
            id_exchange=str(id_exchange) if id_exchange else None,
            id_cliente=id_cliente,
            par=str(crudo.get("symbol") or par),
            lado=lado,
            tipo=tipo,
            cantidad=decimal(crudo.get("amount")) or cantidad,
            ejecutada=ejecutada,
            precio_medio=medio,
            comision=comision,
            comision_moneda=moneda,
            estado=estado_de(crudo),
            at=_momento(crudo.get("timestamp")) or self._reloj(),
        )

    def _de_ccxt(self, crudo: Mapping[str, Any], id_cliente: str | None = None) -> OrdenExchange:
        """Una orden leída del exchange, sin saber lo que se pidió: lo dice ella."""
        id_ex = str(crudo.get("clientOrderId") or "")
        lado: Lado = "venta" if crudo.get("side") == "sell" else "compra"
        tipo: Literal["mercado", "limite"] = (
            "mercado" if crudo.get("type") == "market" else "limite"
        )
        return self._orden(
            crudo,
            id_cliente or self._ids.get(id_ex, id_ex),
            str(crudo.get("symbol") or ""),
            lado,
            tipo,
            decimal(crudo.get("amount")) or Decimal(0),
        )

    def orden(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        self._exigir_claves()
        self._mercado_ccxt(par)
        id_ex = id_en_el_exchange(self._ficha.formato_id, id_cliente)
        with self._cerrojo:
            crudo = self._buscar_o_fallar(par, id_ex, f"consultar la orden {id_cliente}")
            if crudo is None:
                return None
            return self._de_ccxt(self._con_comision(par, crudo), id_cliente)

    def cancelar(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        self._exigir_claves()
        self._mercado_ccxt(par)
        id_ex = id_en_el_exchange(self._ficha.formato_id, id_cliente)
        with self._cerrojo:
            crudo = self._buscar_o_fallar(par, id_ex, f"buscar la orden {id_cliente}")
            if crudo is None:
                return None
            if estado_de(crudo) not in ("abierta", "parcial") or crudo.get("status") != "open":
                return self._de_ccxt(crudo, id_cliente)
            try:
                self._ex.cancel_order(str(crudo["id"]), par)
            except Exception as error:
                tipos = tipos_de(error)
                if "OrderNotFound" not in tipos:
                    if es_incierto(error):
                        raise EstadoDesconocidoError(
                            f"Se pidió cancelar la orden {id_cliente} en {self._ficha.nombre} y se "
                            "cortó la comunicación: NO se sabe si se canceló. Consúltala."
                        ) from None
                    raise ExchangeError(self.explicar(error, "cancelar la orden")) from None
            despues = self._buscar_o_none(par, id_ex)
            return self._de_ccxt(despues or crudo, id_cliente)

    def ordenes_abiertas(self, par: str | None = None) -> list[OrdenExchange]:
        self._exigir_claves()
        contado = {s for s, m in self._mercados_ccxt().items() if es_contado(_dict(m))}
        if par is not None and par not in contado:
            self._mercado_ccxt(par)  # el error en llano
        crudas = self._leer("leer las órdenes abiertas", lambda: self._ex.fetch_open_orders(par))
        return [
            self._de_ccxt(_dict(o)) for o in _lista(crudas) if _dict(o).get("symbol") in contado
        ]


def _con_id(ordenes: list[Any], id_ex: str) -> dict[str, Any] | None:
    for orden in ordenes:
        d = _dict(orden)
        if d.get("clientOrderId") == id_ex and d.get("id"):
            return d
    return None


def _niveles(crudos: object, cuantos: int) -> tuple[Nivel, ...]:
    salida: list[Nivel] = []
    for fila in _lista(crudos)[:cuantos]:
        valores = _lista(fila)
        if len(valores) < 2:
            continue
        precio, cantidad = decimal(valores[0]), decimal(valores[1])
        if precio is not None and cantidad is not None:
            salida.append(Nivel(precio=precio, cantidad=cantidad))
    return tuple(salida)


def _txt(numero: Decimal | None) -> str:
    """Un número sin ceros de más ni notación científica ('0.0001', '10')."""
    if numero is None:
        return "?"
    return format(numero.normalize(), "f")
