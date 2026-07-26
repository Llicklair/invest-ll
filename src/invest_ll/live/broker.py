"""La frontera con el dinero.

**`Confirmation` no tiene valor por defecto y se construye con la orden concreta que autoriza.**
Eso significa que "autorizar todas las órdenes" no se puede escribir: no hay forma de construir
una confirmación genérica. Es FR-028 impuesto por el tipo en lugar de por un `if` que alguien
puede olvidar poner.

`SimulatedBroker` no manda nada al exterior con **ninguna** confirmación. Esa es la garantía que
protege el estado por defecto del sistema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable

from invest_ll.errors import InvestLLError
from invest_ll.live.mode import OperatingMode, Simulation


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    """Se envio y se perdio la conexion. NO se sabe si se ejecuto (FR-035)."""


class ExecutionError(InvestLLError):
    """No se pudo ejecutar la orden."""


class ConfirmationMismatchError(InvestLLError):
    """La confirmación no corresponde a esta orden."""


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Lo que se quiere ejecutar."""

    symbol: str
    side: Side
    quantity: Decimal
    requested_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("una orden necesita simbolo")
        if self.quantity <= 0:
            raise ValueError(f"cantidad no positiva: {self.quantity}")
        if self.requested_at.tzinfo is None:
            raise ValueError("la fecha de la orden necesita zona horaria")

    @property
    def fingerprint(self) -> str:
        """Lo que identifica a esta orden y a ninguna otra."""
        return f"{self.symbol}|{self.side.value}|{self.quantity}|{self.requested_at.isoformat()}"


@dataclass(frozen=True, slots=True)
class Confirmation:
    """Autorización para **una** orden concreta.

    Se construye a partir de la orden, así que no existe forma de fabricar una confirmación
    "para todo". Si la orden cambia entre la confirmación y el envío, la huella deja de coincidir
    y el envío se rechaza.
    """

    fingerprint: str
    confirmed_at: datetime

    @classmethod
    def para(cls, request: OrderRequest, *, at: datetime) -> Confirmation:
        return cls(fingerprint=request.fingerprint, confirmed_at=at)

    def authorises(self, request: OrderRequest) -> bool:
        return self.fingerprint == request.fingerprint


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Lo que realmente ocurrió."""

    request: OrderRequest
    status: OrderStatus
    filled_quantity: Decimal
    fill_price: Decimal | None
    executed_at: datetime | None
    broker_reference: str | None = None
    commission: Decimal | None = None
    """Lo que se quedó el exchange. `None` es **desconocida**, no cero.

    Sin este dato, todo lo que se construya encima del registro miente por omisión: la comisión se
    cobra igual, solo que deja de aparecer en tus cifras. Distinguir «no cobraron» de «no lo
    apuntamos» es lo que permite que una cartera derivada de aquí avise en vez de inventar.
    """

    def __post_init__(self) -> None:
        if self.commission is not None and self.commission < 0:
            raise ValueError(f"una comision negativa ({self.commission}) seria un ingreso disfrazado")

    @property
    def matches_request(self) -> bool:
        return self.status is OrderStatus.FILLED and self.filled_quantity == self.request.quantity

    @property
    def needs_attention(self) -> bool:
        """Cualquier cosa que no sea 'salió exactamente como se pidió' (FR-031)."""
        return not self.matches_request

    def describe(self) -> str:
        if self.status is OrderStatus.UNKNOWN:
            return (
                f"{self.request.symbol}: ESTADO DESCONOCIDO. Se envio la orden y se perdio la "
                "conexion. NO se asume que se ejecuto ni que fallo — compruebalo en el exchange "
                "antes de volver a operar."
            )
        if self.status is OrderStatus.REJECTED:
            return f"{self.request.symbol}: rechazada."
        if self.status is OrderStatus.PARTIAL:
            return (
                f"{self.request.symbol}: ejecutada solo en parte "
                f"({self.filled_quantity} de {self.request.quantity})."
            )
        if not self.matches_request:
            return (
                f"{self.request.symbol}: ejecutada {self.filled_quantity}, "
                f"se pidieron {self.request.quantity}."
            )
        return f"{self.request.symbol}: ejecutada {self.filled_quantity} a {self.fill_price}."


@runtime_checkable
class Broker(Protocol):
    """Quien ejecuta órdenes."""

    @property
    def mode(self) -> OperatingMode: ...

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult: ...

    def balance(self) -> dict[str, Decimal]: ...


class SimulatedBroker:
    """No manda nada. Ni con confirmación, ni sin ella.

    Es el broker por defecto, y su única promesa es que **ninguna orden sale al exterior**. Todo
    lo que hace es registrar lo que habría hecho.
    """

    __slots__ = ("_balance", "_mode", "_submitted")

    def __init__(self, balance: dict[str, Decimal] | None = None) -> None:
        self._mode = Simulation()
        self._balance = dict(balance or {})
        self._submitted: list[OrderRequest] = []

    @property
    def mode(self) -> Simulation:
        return self._mode

    @property
    def submitted(self) -> tuple[OrderRequest, ...]:
        """Lo que se habría enviado. Para poder revisarlo antes de ir en serio."""
        return tuple(self._submitted)

    def submit(self, request: OrderRequest, *, confirmation: Confirmation) -> OrderResult:
        if not confirmation.authorises(request):
            raise ConfirmationMismatchError(
                "la confirmacion no corresponde a esta orden. Cada orden se autoriza por separado."
            )

        self._submitted.append(request)
        # Nada sale de aqui. Es el motivo entero de que esta clase exista.
        return OrderResult(
            request=request,
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            fill_price=None,
            executed_at=request.requested_at,
            broker_reference="simulacion",
        )

    def balance(self) -> dict[str, Decimal]:
        return dict(self._balance)
