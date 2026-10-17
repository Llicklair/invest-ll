"""Lo que se le puede pedir a la fuente de precios en vivo, sin saber cuál es.

La cuenta de práctica y los bots solo conocen este protocolo. La fuente de verdad (Hyperliquid, por
su API pública) lo implementa en su módulo; las pruebas usan `FuenteFalsa`, que no toca la red.

Una fuente guarda en memoria lo último que sabe y lo da al momento: pedir un precio nunca espera a
la red. Lo que no sabe, lo dice con `None` (o lista vacía): no se inventa un precio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable

INTERVALOS = ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "12h", "1d", "3d", "1w", "1M")
"""Los intervalos de vela de Hyperliquid."""


@dataclass(frozen=True, slots=True)
class Nivel:
    """Un nivel del libro: a este precio hay esta cantidad (en la moneda) esperando."""

    precio: Decimal
    cantidad: Decimal
    ordenes: int = 1


@dataclass(frozen=True, slots=True)
class Libro:
    """El libro de órdenes de una moneda en un momento.

    `compras` (bids) de mayor a menor precio; `ventas` (asks) de menor a mayor. Quien compra a
    mercado se come las `ventas`; quien vende, las `compras`.
    """

    coin: str
    compras: tuple[Nivel, ...]
    ventas: tuple[Nivel, ...]
    at: datetime

    @property
    def mejor_compra(self) -> Decimal | None:
        return self.compras[0].precio if self.compras else None

    @property
    def mejor_venta(self) -> Decimal | None:
        return self.ventas[0].precio if self.ventas else None

    @property
    def medio(self) -> Decimal | None:
        if self.mejor_compra is None or self.mejor_venta is None:
            return None
        return (self.mejor_compra + self.mejor_venta) / 2


@dataclass(frozen=True, slots=True)
class Vela:
    """Una vela. `cerrada=False` es la que está en curso y aún se mueve."""

    coin: str
    intervalo: str
    inicio: datetime
    fin: datetime
    apertura: Decimal
    maximo: Decimal
    minimo: Decimal
    cierre: Decimal
    volumen: Decimal
    cerrada: bool


class FuentePrecios(Protocol):
    """Lo que la cuenta de práctica y los bots piden a los precios en vivo."""

    def conectada(self) -> bool:
        """Si ahora mismo llegan datos. Desconectada, lo que se tenga puede estar viejo."""
        ...

    def seguir(self, coin: str, *, libro: bool = False, intervalos: Iterable[str] = ()) -> None:
        """Pide que se mantengan al día el libro y/o las velas de esa moneda (suscribirse)."""
        ...

    def precio(self, coin: str) -> Decimal | None:
        """El precio medio más reciente de la moneda, o `None` si no se conoce."""
        ...

    def libro(self, coin: str) -> Libro | None:
        """La última foto del libro de la moneda (hay que haberla pedido con `seguir`)."""
        ...

    def velas(self, coin: str, intervalo: str, limite: int = 500) -> list[Vela]:
        """Las últimas `limite` velas, de la más antigua a la más reciente; la última puede estar
        en curso (`cerrada=False`). Vacía si aún no se conocen."""
        ...


@dataclass(slots=True)
class FuenteFalsa:
    """Una fuente en memoria para las pruebas: lo que se le pone es lo que devuelve."""

    precios: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    libros: dict[str, Libro] = field(default_factory=dict[str, Libro])
    series: dict[tuple[str, str], list[Vela]] = field(
        default_factory=dict[tuple[str, str], list[Vela]]
    )
    seguidas: set[tuple[str, bool, tuple[str, ...]]] = field(
        default_factory=set[tuple[str, bool, tuple[str, ...]]]
    )
    conectada_: bool = True

    def conectada(self) -> bool:
        return self.conectada_

    def seguir(self, coin: str, *, libro: bool = False, intervalos: Iterable[str] = ()) -> None:
        self.seguidas.add((coin, libro, tuple(intervalos)))

    def precio(self, coin: str) -> Decimal | None:
        if coin in self.precios:
            return self.precios[coin]
        libro = self.libros.get(coin)
        return libro.medio if libro is not None else None

    def libro(self, coin: str) -> Libro | None:
        return self.libros.get(coin)

    def velas(self, coin: str, intervalo: str, limite: int = 500) -> list[Vela]:
        return list(self.series.get((coin, intervalo), []))[-limite:]
