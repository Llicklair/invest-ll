"""La cuenta de práctica: comprar y vender con USDC ficticios a precios reales (docs/panel-v3-vivo.md §2).

Nada sale al exterior. Las órdenes se ejecutan con `vivo/ejecucion.py` contra el libro **real** del
momento que da la fuente de precios:

- **A mercado**, ya, nivel a nivel y con comisión de tomador. Si aún no hay libro de esa moneda se
  pide (`seguir`) y se dice "prueba en un segundo": no se inventa un precio. Sin conexión, tampoco
  se opera (el libro que hay puede ser viejo).
- **Con límite**, queda pendiente y aparta lo necesario: los USDC de una compra (precio por cantidad
  más la comisión de creador) y la moneda de una venta. Se ejecuta a su precio, con comisión de
  creador, cuando el libro la cruza (`revisar`, que el panel llama en un bucle). Si al ponerla ya
  cruza, se ejecuta al momento contra el libro como tomador, sin pasar de su precio.
- No se vende lo que no se tiene ni se compra sin saldo. Una compra por importe que se pasa solo por
  la comisión (el "100 % del saldo") se ajusta para que quepa, y se dice.
- Las cantidades se recortan (hacia abajo) a los decimales que admite la moneda en Hyperliquid.

**En disco** (`practica/`, fuera de git): `registro.jsonl`, un registro que solo añade (cada línea,
un hecho: el inicio, una orden, una cancelación, una ejecución), escrito de forma atómica. La cuenta
es lo que resulta de repasarlo. Reiniciar guarda el registro anterior en `practica/anteriores/`.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from invest_ll import llano
from invest_ll.errors import InvestLLError
from invest_ll.nombres import nombre_hyperliquid
from invest_ll.vivo.ejecucion import (
    COMISIONES,
    Comisiones,
    LibroInsuficienteError,
    a_limite,
    a_mercado,
    limite_cruza,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from invest_ll.vivo.ejecucion import Ejecucion
    from invest_ll.vivo.fuente import FuentePrecios, Libro

log = logging.getLogger(__name__)

CARPETA: Final = Path("practica")
REGISTRO: Final = "registro.jsonl"
ANTERIORES: Final = "anteriores"
INICIAL: Final = Decimal(10000)
MONEDA: Final = "USDC"
DECIMALES_USDC: Final = 6
UNA_MILLONESIMA: Final = Decimal("0.000001")
DECIMALES_PRECIO: Final = 8
HISTORIAL_VISIBLE: Final = 200
"""Ejecuciones que se enseñan (las más recientes); el registro las guarda todas."""

Lado = Literal["compra", "venta"]
Tipo = Literal["mercado", "limite"]


class PracticaError(InvestLLError):
    """Lo que la cuenta de práctica no deja hacer. El texto es para enseñarlo tal cual."""


class SinLibroError(PracticaError):
    """Aún no ha llegado el libro de la moneda."""


class SinConexionError(PracticaError):
    """No llegan datos: el libro que hay puede ser viejo."""


class SinSaldoError(PracticaError):
    """No hay USDC libres para la compra."""


class SinMonedaError(PracticaError):
    """No se tiene (libre) la cantidad que se quiere vender."""


class OrdenNoEncontradaError(LookupError):
    """No hay ninguna orden pendiente con ese número."""


def _ahora() -> datetime:
    return datetime.now(UTC)


def limpio(valor: Decimal) -> Decimal:
    """La misma cifra sin ceros de más a la derecha (`0.45000` -> `0.45`, `995.0` -> `995`)."""
    if valor == valor.to_integral_value():
        return valor.quantize(Decimal(1))
    return valor.normalize()


def recortar(valor: Decimal, decimales: int, redondeo: str = ROUND_HALF_UP) -> Decimal:
    """Como mucho `decimales` decimales y sin ceros de más (`81173.5` se queda igual)."""
    exponente = valor.as_tuple().exponent
    if isinstance(exponente, int) and exponente < -decimales:
        valor = valor.quantize(Decimal(1).scaleb(-decimales), rounding=redondeo)
    return limpio(valor)


def _a_la_baja(cantidad: Decimal, decimales: int | None) -> Decimal:
    if decimales is None:
        return cantidad
    return recortar(cantidad, decimales, ROUND_DOWN)


# -- Lo que hay en la cuenta -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Posicion:
    """Lo que tienes de una moneda. `coste`: lo que te costó, comisiones incluidas."""

    coin: str
    cantidad: Decimal
    coste: Decimal

    @property
    def precio_medio(self) -> Decimal:
        return recortar(self.coste / self.cantidad, DECIMALES_PRECIO)


@dataclass(frozen=True, slots=True)
class Orden:
    """Una orden con límite pendiente. `reservado`: los USDC apartados (solo en las compras)."""

    id: str
    coin: str
    lado: Lado
    cantidad: Decimal
    precio_limite: Decimal
    reservado: Decimal
    creada: datetime


@dataclass(frozen=True, slots=True)
class Ejecutada:
    """Una compra o venta hecha. `importe`, sin la comisión; `precio`, el medio."""

    id: str
    coin: str
    lado: Lado
    tipo: Tipo
    cantidad: Decimal
    precio: Decimal
    importe: Decimal
    comision: Decimal
    at: datetime
    orden_id: str | None = None

    @property
    def neto(self) -> Decimal:
        """Lo que sale (compra) o entra (venta) de USDC, comisión incluida."""
        return (
            self.importe + self.comision if self.lado == "compra" else self.importe - self.comision
        )


@dataclass(frozen=True, slots=True)
class Resultado:
    """Lo que pasó al mandar una orden: se ejecutó ya (`ejecutada`) o quedó pendiente (`orden`)."""

    ejecutada: Ejecutada | None
    orden: Orden | None
    ajustada: bool = False

    @property
    def resumen(self) -> str:
        return resumir(self)


@dataclass(slots=True)
class _Estado:
    inicial: Decimal
    saldo: Decimal
    posiciones: dict[str, Posicion] = field(default_factory=dict[str, Posicion])
    ordenes: dict[str, Orden] = field(default_factory=dict[str, Orden])
    historial: list[Ejecutada] = field(default_factory=list[Ejecutada])

    @property
    def reservado(self) -> Decimal:
        return sum((o.reservado for o in self.ordenes.values()), Decimal(0))


@dataclass(frozen=True, slots=True)
class Foto:
    """La cuenta en un momento, sin valorar. `historial`: las `HISTORIAL_VISIBLE` ejecuciones
    más recientes, la última primero."""

    inicial: Decimal
    saldo: Decimal
    reservado: Decimal
    posiciones: tuple[Posicion, ...]
    ordenes: tuple[Orden, ...]
    historial: tuple[Ejecutada, ...]


# -- Los hechos del registro -----------------------------------------------------------------------


def _hecho_ejecutada(e: Ejecutada) -> dict[str, Any]:
    return {
        "hecho": "ejecucion",
        "at": e.at.isoformat(),
        "id": e.id,
        "coin": e.coin,
        "lado": e.lado,
        "tipo": e.tipo,
        "cantidad": str(e.cantidad),
        "precio": str(e.precio),
        "importe": str(e.importe),
        "comision": str(e.comision),
        "orden_id": e.orden_id,
    }


def _hecho_orden(o: Orden) -> dict[str, Any]:
    return {
        "hecho": "orden",
        "at": o.creada.isoformat(),
        "id": o.id,
        "coin": o.coin,
        "lado": o.lado,
        "cantidad": str(o.cantidad),
        "precio_limite": str(o.precio_limite),
        "reservado": str(o.reservado),
    }


def _aplicar(estado: _Estado, hecho: dict[str, Any]) -> None:
    """Lo que cambia un hecho del registro. El mismo para operar y para repasar el registro."""
    tipo = hecho["hecho"]
    if tipo == "inicio":
        inicial = Decimal(hecho["inicial"])
        estado.inicial, estado.saldo = inicial, inicial
        estado.posiciones.clear()
        estado.ordenes.clear()
        estado.historial.clear()
    elif tipo == "orden":
        orden = Orden(
            id=hecho["id"],
            coin=hecho["coin"],
            lado=hecho["lado"],
            cantidad=Decimal(hecho["cantidad"]),
            precio_limite=Decimal(hecho["precio_limite"]),
            reservado=Decimal(hecho["reservado"]),
            creada=datetime.fromisoformat(hecho["at"]),
        )
        estado.ordenes[orden.id] = orden
        estado.saldo -= orden.reservado
    elif tipo == "cancelacion":
        orden = estado.ordenes.pop(hecho["id"])
        estado.saldo += orden.reservado
    elif tipo == "ejecucion":
        e = Ejecutada(
            id=hecho["id"],
            coin=hecho["coin"],
            lado=hecho["lado"],
            tipo=hecho["tipo"],
            cantidad=Decimal(hecho["cantidad"]),
            precio=Decimal(hecho["precio"]),
            importe=Decimal(hecho["importe"]),
            comision=Decimal(hecho["comision"]),
            at=datetime.fromisoformat(hecho["at"]),
            orden_id=hecho.get("orden_id"),
        )
        if e.orden_id is not None:
            orden = estado.ordenes.pop(e.orden_id)
            estado.saldo += orden.reservado  # lo apartado vuelve y se paga abajo, como siempre
        previa = estado.posiciones.get(e.coin)
        if e.lado == "compra":
            estado.saldo -= e.neto
            cantidad = e.cantidad + (previa.cantidad if previa else Decimal(0))
            coste = e.neto + (previa.coste if previa else Decimal(0))
            estado.posiciones[e.coin] = Posicion(e.coin, cantidad, coste)
        else:
            estado.saldo += e.neto
            if previa is None:  # pragma: no cover - el registro lo impide al escribir
                raise PracticaError(f"el registro vende {e.coin} sin tenerlo")
            queda = previa.cantidad - e.cantidad
            if queda > 0:
                coste = previa.coste * queda / previa.cantidad
                estado.posiciones[e.coin] = Posicion(e.coin, queda, coste)
            else:
                del estado.posiciones[e.coin]
        estado.historial.append(e)
    else:  # pragma: no cover - un hecho de una versión futura
        log.warning("Hecho desconocido en el registro de práctica: %s", tipo)


# -- La cuenta ---------------------------------------------------------------------------------------


class CuentaDePractica:
    """La cuenta de práctica guardada en `carpeta`. Se puede usar desde varios hilos a la vez."""

    def __init__(
        self,
        carpeta: Path = CARPETA,
        *,
        reloj: Callable[[], datetime] = _ahora,
        comisiones: Comisiones = COMISIONES,
    ) -> None:
        self.carpeta = carpeta
        self._reloj = reloj
        self._comisiones = comisiones
        self._cerrojo = threading.RLock()
        self._estado = _Estado(inicial=INICIAL, saldo=INICIAL)
        self._empezada = False
        self._cargar()

    @property
    def registro(self) -> Path:
        return self.carpeta / REGISTRO

    # -- Mirar -------------------------------------------------------------------------------------

    def foto(self) -> Foto:
        with self._cerrojo:
            e = self._estado
            return Foto(
                inicial=e.inicial,
                saldo=e.saldo,
                reservado=e.reservado,
                posiciones=tuple(sorted(e.posiciones.values(), key=lambda p: p.coin)),
                ordenes=tuple(sorted(e.ordenes.values(), key=lambda o: o.creada)),
                historial=tuple(reversed(e.historial[-HISTORIAL_VISIBLE:])),
            )

    def disponible(self, coin: str) -> Decimal:
        """Lo que se tiene de la moneda menos lo apartado por órdenes de venta pendientes."""
        with self._cerrojo:
            posicion = self._estado.posiciones.get(coin)
            tenida = posicion.cantidad if posicion else Decimal(0)
            apartada = sum(
                (
                    o.cantidad
                    for o in self._estado.ordenes.values()
                    if o.coin == coin and o.lado == "venta"
                ),
                Decimal(0),
            )
            return tenida - apartada

    def monedas_con_ordenes(self) -> set[str]:
        with self._cerrojo:
            return {o.coin for o in self._estado.ordenes.values()}

    # -- Operar ------------------------------------------------------------------------------------

    def a_mercado(
        self,
        fuente: FuentePrecios,
        coin: str,
        lado: Lado,
        *,
        cantidad: Decimal | None = None,
        importe: Decimal | None = None,
        decimales: int | None = None,
    ) -> Resultado:
        """Compra o vende ya, contra el libro de este momento. `cantidad` en la moneda o
        `importe` en USDC (sin la comisión), uno de los dos."""
        if (cantidad is None) == (importe is None):
            raise PracticaError(
                "Di la cantidad (en la moneda) o el importe (en USDC), uno de los dos."
            )
        libro = self._libro(fuente, coin)
        with self._cerrojo:
            if lado == "venta" and cantidad is not None:
                self._comprobar_que_tienes(coin, _a_la_baja(cantidad, decimales))
            ajustada = False
            hecha = self._nueva_ejecutada(
                coin, lado, "mercado", self._ejecutar(libro, lado, cantidad, importe, decimales)
            )
            saldo = self._estado.saldo
            if lado == "compra" and hecha.neto > saldo:
                if importe is not None and importe <= saldo:
                    # El "100 % del saldo": lo que se pasa es la comisión. Se compra lo que cabe
                    # (con una millonésima de margen para el redondeo de la comisión).
                    cabe = recortar(
                        (saldo - UNA_MILLONESIMA) / (1 + self._comisiones.tomador),
                        DECIMALES_USDC,
                        ROUND_DOWN,
                    )
                    hecha = self._nueva_ejecutada(
                        coin, lado, "mercado", self._ejecutar(libro, lado, None, cabe, decimales)
                    )
                    ajustada = True
                if hecha.neto > saldo:
                    raise self._sin_saldo(hecha.neto)
            if lado == "venta":
                self._comprobar_que_tienes(coin, hecha.cantidad)
            self._anotar(_hecho_ejecutada(hecha))
            return Resultado(ejecutada=hecha, orden=None, ajustada=ajustada)

    def con_limite(
        self,
        fuente: FuentePrecios,
        coin: str,
        lado: Lado,
        *,
        cantidad: Decimal,
        precio_limite: Decimal,
        decimales: int | None = None,
    ) -> Resultado:
        """Una orden con límite. Si ya cruza el libro, se ejecuta al momento sin pasar de su
        precio; si no, queda pendiente apartando lo necesario."""
        if cantidad <= 0 or precio_limite <= 0:
            raise PracticaError("La cantidad y el precio límite tienen que ser mayores que cero.")
        cantidad = _a_la_baja(cantidad, decimales)
        if cantidad <= 0:
            raise PracticaError(f"La cantidad es demasiado pequeña: {_minimo(coin, decimales)}.")
        libro = self._libro(fuente, coin)
        with self._cerrojo:
            if lado == "venta":
                self._comprobar_que_tienes(coin, cantidad)
            if limite_cruza(libro, lado, precio_limite):
                try:
                    ejecucion = a_mercado(
                        _hasta(libro, lado, precio_limite),
                        lado,
                        cantidad=cantidad,
                        comisiones=self._comisiones,
                    )
                except LibroInsuficienteError as error:
                    raise PracticaError(
                        f"Tu precio ya cruza el libro, pero hasta ese precio no hay bastante para "
                        f"toda la orden ({error}). Pon menos cantidad o un precio que no cruce, y "
                        "quedará pendiente."
                    ) from error
                hecha = self._nueva_ejecutada(coin, lado, "limite", ejecucion)
                if lado == "compra" and hecha.neto > self._estado.saldo:
                    raise self._sin_saldo(hecha.neto)
                self._anotar(_hecho_ejecutada(hecha))
                return Resultado(ejecutada=hecha, orden=None)

            reservado = Decimal(0)
            if lado == "compra":
                importe = cantidad * precio_limite
                reservado = importe + recortar(
                    importe * self._comisiones.creador, DECIMALES_USDC, ROUND_UP
                )
                if reservado > self._estado.saldo:
                    raise self._sin_saldo(reservado)
            orden = Orden(
                id=_nuevo_id(),
                coin=coin,
                lado=lado,
                cantidad=cantidad,
                precio_limite=precio_limite,
                reservado=reservado,
                creada=self._reloj(),
            )
            self._anotar(_hecho_orden(orden))
        fuente.seguir(coin, libro=True)
        return Resultado(ejecutada=None, orden=orden)

    def cancelar(self, orden_id: str) -> Orden:
        with self._cerrojo:
            orden = self._estado.ordenes.get(orden_id)
            if orden is None:
                raise OrdenNoEncontradaError(orden_id)
            self._anotar({"hecho": "cancelacion", "at": self._reloj().isoformat(), "id": orden_id})
            return orden

    def revisar(self, fuente: FuentePrecios) -> list[Ejecutada]:
        """Ejecuta las órdenes con límite que el libro de ahora cruza. Sin conexión no hace nada:
        el libro que hay puede ser viejo."""
        hechas: list[Ejecutada] = []
        with self._cerrojo:
            pendientes = list(self._estado.ordenes.values())
        if not pendientes or not fuente.conectada():
            return hechas
        for orden in pendientes:
            libro = fuente.libro(orden.coin)
            if libro is None:
                fuente.seguir(orden.coin, libro=True)
                continue
            if not limite_cruza(libro, orden.lado, orden.precio_limite):
                continue
            with self._cerrojo:
                if orden.id not in self._estado.ordenes:  # cancelada mientras tanto
                    continue
                ejecucion = a_limite(
                    orden.lado, orden.cantidad, orden.precio_limite, comisiones=self._comisiones
                )
                hecha = replace(
                    self._nueva_ejecutada(orden.coin, orden.lado, "limite", ejecucion),
                    orden_id=orden.id,
                )
                self._anotar(_hecho_ejecutada(hecha))
                hechas.append(hecha)
        return hechas

    def reiniciar(self, inicial: Decimal = INICIAL) -> Path | None:
        """Empieza de cero con `inicial` USDC. El registro anterior se guarda en
        `anteriores/` (se devuelve dónde; `None` si no había nada que guardar)."""
        if inicial <= 0:
            raise PracticaError("El saldo inicial tiene que ser mayor que cero.")
        with self._cerrojo:
            guardado: Path | None = None
            if self.registro.exists():
                destino = self.carpeta / ANTERIORES
                destino.mkdir(parents=True, exist_ok=True)
                guardado = destino / f"registro-{self._reloj():%Y%m%d-%H%M%S}-{_nuevo_id()}.jsonl"
                os.replace(self.registro, guardado)  # noqa: PTH105 - mismo patrón que el resto
            self._estado = _Estado(inicial=INICIAL, saldo=INICIAL)
            self._empezada = False
            self._anotar(
                {"hecho": "inicio", "at": self._reloj().isoformat(), "inicial": str(inicial)}
            )
            return guardado

    # -- Por dentro --------------------------------------------------------------------------------

    def _libro(self, fuente: FuentePrecios, coin: str) -> Libro:
        libro = fuente.libro(coin)
        if libro is None:
            fuente.seguir(coin, libro=True)
            raise SinLibroError(
                f"Aún no hay libro de {nombre_hyperliquid(coin)}, prueba en un segundo."
            )
        if not fuente.conectada():
            raise SinConexionError(
                "Ahora mismo no llegan datos de Hyperliquid y el libro que hay puede ser viejo: "
                "no se opera con precios viejos. Prueba en unos segundos."
            )
        return libro

    def _ejecutar(
        self,
        libro: Libro,
        lado: Lado,
        cantidad: Decimal | None,
        importe: Decimal | None,
        decimales: int | None,
    ) -> Ejecucion:
        """`a_mercado` con la cantidad recortada a los decimales de la moneda. Si el libro no da
        para tanto, se dice cuánto hay (no se inventa precio)."""
        try:
            if cantidad is not None:
                redondeada = _a_la_baja(cantidad, decimales)
                if redondeada <= 0:
                    raise PracticaError(
                        f"La cantidad es demasiado pequeña: {_minimo(libro.coin, decimales)}."
                    )
                return a_mercado(libro, lado, cantidad=redondeada, comisiones=self._comisiones)
            ejecucion = a_mercado(libro, lado, importe=importe, comisiones=self._comisiones)
            redondeada = _a_la_baja(ejecucion.cantidad, decimales)
            if redondeada <= 0:
                raise PracticaError(
                    f"El importe es demasiado pequeño: {_minimo(libro.coin, decimales)}."
                )
            if redondeada != ejecucion.cantidad:
                ejecucion = a_mercado(libro, lado, cantidad=redondeada, comisiones=self._comisiones)
            return ejecucion
        except LibroInsuficienteError as error:
            texto = str(error)
            raise PracticaError(f"{texto[:1].upper()}{texto[1:]}.") from error

    def _comprobar_que_tienes(self, coin: str, cantidad: Decimal) -> None:
        libre = self.disponible(coin)
        nombre = nombre_hyperliquid(coin)
        if libre <= 0:
            raise SinMonedaError(f"No tienes {nombre} para vender.")
        if cantidad > libre:
            raise SinMonedaError(
                f"Solo tienes {llano.cantidad(libre)} de {nombre} libres para vender "
                f"y la orden es de {llano.cantidad(cantidad)}."
            )

    def _sin_saldo(self, necesario: Decimal) -> SinSaldoError:
        return SinSaldoError(
            f"No te llega: son {usdc(necesario)} con la comisión y tienes "
            f"{usdc(self._estado.saldo)} libres."
        )

    def _nueva_ejecutada(self, coin: str, lado: Lado, tipo: Tipo, e: Ejecucion) -> Ejecutada:
        return Ejecutada(
            id=_nuevo_id(),
            coin=coin,
            lado=lado,
            tipo=tipo,
            cantidad=limpio(e.cantidad),
            precio=recortar(e.precio_medio, DECIMALES_PRECIO),
            importe=limpio(e.importe),
            comision=recortar(e.comision, DECIMALES_USDC),
            at=self._reloj(),
        )

    def _cargar(self) -> None:
        if not self.registro.exists():
            return
        for numero, linea in enumerate(self.registro.read_text(encoding="utf-8").splitlines(), 1):
            if not linea.strip():
                continue
            try:
                _aplicar(self._estado, json.loads(linea))
            except (ValueError, KeyError, TypeError, InvalidOperation) as error:
                log.warning(
                    "Línea %s del registro de práctica que no se entiende (%s): se salta",
                    numero,
                    error,
                )
        self._empezada = True

    def _anotar(self, hecho: dict[str, Any]) -> None:
        """Añade el hecho al registro (de forma atómica) y después lo aplica. Si no se puede
        escribir, la cuenta no cambia."""
        hechos = [hecho]
        if not self._empezada and hecho["hecho"] != "inicio":
            inicio = {
                "hecho": "inicio",
                "at": self._reloj().isoformat(),
                "inicial": str(self._estado.inicial),
            }
            hechos.insert(0, inicio)
        lineas = "".join(json.dumps(h, ensure_ascii=False) + "\n" for h in hechos)
        _anadir(self.registro, lineas)
        self._empezada = True
        for h in hechos:
            _aplicar(self._estado, h)


def _anadir(destino: Path, lineas: str) -> None:
    """Escribe el registro con las líneas nuevas al final: temporal en la misma carpeta y
    `os.replace`, que es atómico (también en Windows). Un corte deja el anterior o el nuevo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    previo = destino.read_bytes() if destino.exists() else b""
    fd, temporal = tempfile.mkstemp(dir=destino.parent, prefix=".tmp-", suffix=".jsonl")
    try:
        with os.fdopen(fd, "wb") as fichero:
            fichero.write(previo)
            fichero.write(lineas.encode("utf-8"))
        os.replace(temporal, destino)  # noqa: PTH105 - el punto exacto donde se vuelve atómico
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def _nuevo_id() -> str:
    return secrets.token_hex(5)


def _hasta(libro: Libro, lado: Lado, precio_limite: Decimal) -> Libro:
    """El libro sin los niveles que pasan del precio límite (para una orden con límite que ya
    cruza: se ejecuta como a mercado, pero sin pagar más ni cobrar menos que su precio)."""
    if lado == "compra":
        return replace(libro, ventas=tuple(n for n in libro.ventas if n.precio <= precio_limite))
    return replace(libro, compras=tuple(n for n in libro.compras if n.precio >= precio_limite))


def _minimo(coin: str, decimales: int | None) -> str:
    if decimales is None:
        return "no llega a nada"
    minimo = Decimal(1).scaleb(-decimales)
    return f"lo mínimo es {llano.cantidad(minimo)} de {nombre_hyperliquid(coin)}"


# -- En llano --------------------------------------------------------------------------------------


def usdc(importe: Decimal) -> str:
    """Un importe en USDC con céntimos ('999,89 USDC'); por debajo del céntimo, con las cifras
    que hagan falta para que no se lea 0,00."""
    if abs(importe) >= Decimal("0.01") or importe == 0:
        return f"{llano.numero(importe, 2)} {MONEDA}"
    return llano.dinero(importe, MONEDA)


def resumir(resultado: Resultado) -> str:
    """'Compraste 0,0148 Bitcoin a 67.420,10 USDC de media: 997,82 USDC más 0,45 de comisión.'"""
    e, orden = resultado.ejecutada, resultado.orden
    if e is not None:
        nombre = nombre_hyperliquid(e.coin)
        cuanto = f"{llano.cantidad(e.cantidad)} {nombre}"
        precio = llano.dinero(e.precio, MONEDA)
        comision = usdc(e.comision)
        if e.lado == "compra":
            texto = (
                f"Compraste {cuanto} a {precio} de media: {usdc(e.importe)} "
                f"más {comision} de comisión."
            )
        else:
            texto = (
                f"Vendiste {cuanto} a {precio} de media: cobras "
                f"{usdc(e.neto)} ({comision} de comisión)."
            )
        if e.tipo == "limite":
            texto = f"Tu precio ya cruzaba el libro y se ejecutó al momento. {texto}"
        if resultado.ajustada:
            texto += " Ajustada para que la comisión quepa en tu saldo."
        return texto
    assert orden is not None
    nombre = nombre_hyperliquid(orden.coin)
    cuanto = f"{llano.cantidad(orden.cantidad)} {nombre}"
    precio = llano.dinero(orden.precio_limite, MONEDA)
    if orden.lado == "compra":
        return (
            f"Orden puesta: comprar {cuanto} cuando alguien venda a {precio} o menos. "
            f"Se apartan {usdc(orden.reservado)} de tu saldo hasta entonces."
        )
    return f"Orden puesta: vender {cuanto} cuando alguien compre a {precio} o más."
