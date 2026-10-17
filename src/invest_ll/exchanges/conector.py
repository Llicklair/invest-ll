"""Lo que se le puede pedir a un exchange, sin saber cuál es (docs/panel-v4-real.md §1).

Los bots reales, las pruebas de estrategias sobre el pasado y Conexiones solo conocen este
protocolo. La implementación genérica (ccxt) y lo propio de cada exchange viven en este paquete; las
pruebas usan un conector falso. **Solo contado (spot), sin apalancamiento.**

Toda cifra de dinero o cantidad es Decimal. Lo que no se sabe se dice con `None`: no se inventa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

from invest_ll.errors import InvestLLError
from invest_ll.vivo.fuente import Libro, Vela

Red = Literal["pruebas", "real"]
Lado = Literal["compra", "venta"]
EstadoOrdenExchange = Literal[
    "abierta", "ejecutada", "parcial", "cancelada", "rechazada", "desconocido"
]


class ExchangeError(InvestLLError):
    """El exchange dijo que no, o no se pudo hablar con él. El texto, en llano."""


class EstadoDesconocidoError(ExchangeError):
    """Se envió y se perdió la conexión: NO se sabe si se ejecutó. Nunca se adivina."""


@dataclass(frozen=True, slots=True)
class Mercado:
    """Un par de contado del exchange (p. ej. BTC/USDT)."""

    par: str
    base: str
    cotizada: str
    minimo_importe: Decimal | None
    minimo_cantidad: Decimal | None
    paso_cantidad: Decimal | None
    paso_precio: Decimal | None
    comision_tomador: Decimal | None
    comision_creador: Decimal | None


@dataclass(frozen=True, slots=True)
class Permisos:
    """Lo que la clave puede hacer, si el exchange lo dice (`None`: no se sabe)."""

    operar: bool | None
    retirar: bool | None
    texto: str


@dataclass(frozen=True, slots=True)
class OrdenExchange:
    id_exchange: str | None
    id_cliente: str
    par: str
    lado: Lado
    tipo: Literal["mercado", "limite"]
    cantidad: Decimal
    ejecutada: Decimal
    precio_medio: Decimal | None
    comision: Decimal | None
    comision_moneda: str | None
    estado: EstadoOrdenExchange
    at: datetime


class Conector(Protocol):
    """Un exchange en una red (pruebas o real). Los métodos de mercado no necesitan claves."""

    @property
    def exchange(self) -> str: ...

    @property
    def red(self) -> Red: ...

    def mercados(self) -> list[Mercado]:
        """Los pares de contado activos."""
        ...

    def precio(self, par: str) -> Decimal | None: ...

    def libro(self, par: str, niveles: int = 20) -> Libro | None: ...

    def velas(
        self, par: str, intervalo: str, desde: datetime | None = None, limite: int = 1000
    ) -> list[Vela]:
        """Velas de la más antigua a la más reciente (la última puede estar en curso)."""
        ...

    def saldo(self) -> dict[str, Decimal]:
        """Lo disponible por moneda (necesita claves)."""
        ...

    def permisos(self) -> Permisos: ...

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
        """Envía UNA orden. Con el mismo `id_cliente`, un reintento no la duplica.
        `EstadoDesconocidoError` si se corta a medias."""
        ...

    def orden(self, par: str, *, id_cliente: str) -> OrdenExchange | None:
        """Cómo está una orden enviada (para resolver un estado desconocido)."""
        ...

    def cancelar(self, par: str, *, id_cliente: str) -> OrdenExchange | None: ...

    def ordenes_abiertas(self, par: str | None = None) -> list[OrdenExchange]: ...
