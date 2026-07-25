"""El protocolo que aísla a las librerías de terceros (T015).

Lo que consigue: el resto del sistema depende de esta abstracción, no de `ccxt` ni de `yfinance`.
Cuando el proveedor de bolsa se rompa —y se romperá, porque no es una API oficial— el recambio
afecta a un fichero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.data.bar import Bar, Interval


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    """Lo que un proveedor declara sobre sí mismo.

    Las advertencias de calidad se **derivan** de estos campos en lugar de escribirse a mano en
    cada sitio. Así no dependen de que alguien se acuerde: si un proveedor no ajusta precios, el
    aviso sale solo.
    """

    name: str
    supported_intervals: frozenset[Interval]
    adjusts_prices: bool
    includes_delisted: bool
    max_bars_per_request: int

    def __post_init__(self) -> None:
        if not self.supported_intervals:
            raise ValueError(f"el proveedor {self.name!r} no declara ningún intervalo soportado")
        if self.max_bars_per_request <= 0:
            raise ValueError("max_bars_per_request debe ser positivo")


@runtime_checkable
class MarketDataProvider(Protocol):
    """Una sola operación: trae velas. Nada más.

    No sabe de caché, ni de ficheros, ni de discrepancias — todo eso vive por encima y es común a
    todos los proveedores. Mantenerlo así es lo que hace que añadir uno nuevo sea barato.
    """

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Qué sabe hacer este proveedor."""
        ...

    def fetch(
        self,
        symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> Sequence[Bar]:
        """Velas del activo en el rango pedido, en orden cronológico y sin duplicados.

        Obligaciones: marcas en UTC con zona; paginar internamente si el rango excede el límite
        del proveedor; lanzar `UnknownSymbolError` ante activo desconocido en lugar de devolver
        una lista vacía que parezca "sin datos".
        """
        ...
