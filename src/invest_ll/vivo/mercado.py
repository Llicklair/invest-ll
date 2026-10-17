"""Lo que la pantalla de Operar pide al mercado en vivo, además de los precios.

`FuentePrecios` (vivo/fuente.py) es lo que necesitan la cuenta de práctica y los bots: precio,
libro y velas. Operar enseña además la lista de monedas con su variación y su volumen, las últimas
operaciones del mercado y si la conexión está viva. Eso es `Mercado`, que la fuente de Hyperliquid
cumple entera.

Cualquier otra fuente (la `FuenteFalsa` de las pruebas) se envuelve en `MercadoMinimo`, que da lo
que se puede saber de ella sin inventar nada: las monedas de las que tiene precio, ninguna
operación y conectada o no.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

from invest_ll.vivo.fuente import FuenteFalsa, FuentePrecios

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable
    from datetime import datetime

    from invest_ll.vivo.fuente import Libro, Vela

NOMBRE_FUENTE = "Hyperliquid"


@dataclass(frozen=True, slots=True)
class InfoMoneda:
    """Lo que se sabe de una moneda además de su precio.

    `precio_ayer` es el de hace 24 h (para la variación) y `volumen_24h`, lo negociado en ese
    tiempo en USDC. `decimales_cantidad` es cuántos decimales admite la cantidad (en BTC, 5).
    """

    coin: str
    decimales_cantidad: int | None
    precio: Decimal | None
    precio_ayer: Decimal | None
    volumen_24h: Decimal | None

    @property
    def variacion_24h(self) -> float | None:
        """En %, o `None` si falta alguno de los dos precios."""
        if self.precio is None or not self.precio_ayer:
            return None
        return float((self.precio - self.precio_ayer) / self.precio_ayer * 100)


@dataclass(frozen=True, slots=True)
class Operacion:
    """Una operación del mercado. `lado` es el de quien la inició (quien se comió el libro)."""

    coin: str
    at: datetime
    precio: Decimal
    cantidad: Decimal
    lado: Literal["compra", "venta"]
    id: int


@dataclass(frozen=True, slots=True)
class EstadoConexion:
    """Si llegan datos, desde cuándo sin cortes y, si no llegan, qué pasa, en llano."""

    conectada: bool
    desde: datetime | None
    aviso: str | None
    fuente: str = NOMBRE_FUENTE


@runtime_checkable
class Mercado(FuentePrecios, Protocol):
    """La fuente de precios con lo que además enseña la pantalla de Operar."""

    def estado(self) -> EstadoConexion: ...

    def existe(self, coin: str) -> bool | None:
        """Si la moneda existe; `None` si aún no se sabe (la lista no ha llegado)."""
        ...

    def canonica(self, coin: str) -> str:
        """El nombre tal como lo escribe la fuente (`btc` -> `BTC`, `kpepe` -> `kPEPE`); el mismo
        si no la conoce."""
        ...

    def monedas(self) -> list[InfoMoneda]:
        """Todas, las más negociadas primero."""
        ...

    def momento_precios(self) -> datetime | None:
        """Cuándo llegaron los últimos precios de la lista."""
        ...

    def decimales(self, coin: str) -> int | None: ...

    def rellenando(self, coin: str, intervalo: str) -> bool:
        """Si el histórico de esa serie de velas se ha pedido y aún no ha llegado."""
        ...

    def operaciones(self, coin: str, limite: int = 50) -> list[Operacion]:
        """Las últimas, la más reciente primero (hay que haberla seguido con `libro=True`)."""
        ...

    def contador_operaciones(self, coin: str) -> int:
        """Cuántas operaciones de la moneda han llegado desde que se sigue: el stream lo usa
        para saber cuántas son nuevas."""
        ...


class MercadoMinimo:
    """Una `FuentePrecios` cualquiera vista como `Mercado`, sin inventar lo que no da."""

    __slots__ = ("_fuente",)

    def __init__(self, fuente: FuentePrecios) -> None:
        self._fuente = fuente

    # -- FuentePrecios: tal cual ---------------------------------------------------------------

    def conectada(self) -> bool:
        return self._fuente.conectada()

    def seguir(self, coin: str, *, libro: bool = False, intervalos: Iterable[str] = ()) -> None:
        self._fuente.seguir(coin, libro=libro, intervalos=intervalos)

    def precio(self, coin: str) -> Decimal | None:
        return self._fuente.precio(coin)

    def libro(self, coin: str) -> Libro | None:
        return self._fuente.libro(coin)

    def velas(self, coin: str, intervalo: str, limite: int = 500) -> list[Vela]:
        return self._fuente.velas(coin, intervalo, limite)

    # -- Lo demás: lo que se puede saber ---------------------------------------------------------

    def estado(self) -> EstadoConexion:
        conectada = self._fuente.conectada()
        return EstadoConexion(
            conectada=conectada,
            desde=None,
            aviso=None if conectada else "No llegan datos en vivo ahora mismo.",
        )

    def existe(self, coin: str) -> bool | None:
        if self._fuente.precio(coin) is not None or self._fuente.libro(coin) is not None:
            return True
        return None

    def canonica(self, coin: str) -> str:
        return coin

    def monedas(self) -> list[InfoMoneda]:
        conocidas: set[str] = set()
        if isinstance(self._fuente, FuenteFalsa):
            conocidas = set(self._fuente.precios) | set(self._fuente.libros)
        return [
            InfoMoneda(
                coin=coin,
                decimales_cantidad=None,
                precio=self._fuente.precio(coin),
                precio_ayer=None,
                volumen_24h=None,
            )
            for coin in sorted(conocidas)
        ]

    def momento_precios(self) -> datetime | None:
        return None

    def decimales(self, coin: str) -> int | None:
        return None

    def rellenando(self, coin: str, intervalo: str) -> bool:
        return False

    def operaciones(self, coin: str, limite: int = 50) -> list[Operacion]:
        return []

    def contador_operaciones(self, coin: str) -> int:
        return 0


def como_mercado(fuente: FuentePrecios) -> Mercado:
    """La fuente tal cual si ya es un `Mercado`; si no, envuelta en `MercadoMinimo`."""
    if isinstance(fuente, Mercado):
        return fuente
    return MercadoMinimo(fuente)
