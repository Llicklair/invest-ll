"""Los movimientos de la cartera y las posiciones que se derivan de ellos.

**Una posición no se edita: se deriva.** Lo que se registra son movimientos (compra, venta,
depósito, retirada) en un ledger que solo añade; las posiciones salen de ahí. Es el modelo de todos
los gestores serios (Ghostfolio, Portfolio Performance, Wealthfolio), y no por moda: una posición
editable es una opinión, una derivada es un hecho auditable.

La distinción que sostiene todo el paquete: una posición **abierta** tiene P&L no realizado —una
valoración que cambia cada día—; al llegar la cantidad a 0 el episodio se cierra y su P&L pasa a
**realizado**, un hecho que ya no cambia. No se suman nunca en una sola cifra: eso contaría como
ganado dinero que aún puede evaporarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256

from invest_ll.errors import InvestLLError

LONGITUD_ID = 16
CERO = Decimal(0)
UNO = Decimal(1)

FUENTE_MANUAL = "manual"
"""Origen por defecto de un movimiento: tecleado por el operador."""


class LedgerInconsistencyError(InvestLLError):
    """El ledger cuenta una historia imposible, como vender lo que nunca se compró.

    No se "arregla" derivando una cantidad negativa: eso sería un ledger incompleto con aspecto de
    cartera válida, el modo de fallo que más cuesta ver.
    """


class ActivityType(Enum):
    """Qué clase de movimiento es."""

    BUY = "buy"
    SELL = "sell"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"

    @property
    def is_cash(self) -> bool:
        """Dinero que entra o sale del sistema, sin activo de por medio."""
        return self in (ActivityType.DEPOSIT, ActivityType.WITHDRAWAL)


def como_texto(valor: Decimal) -> str:
    """Una cifra legible y exacta: `10`, `3.5`, `0.001` — sin notación científica ni ceros de más."""
    return format(valor.normalize(), "f")


@dataclass(frozen=True, slots=True)
class Activity:
    """Un movimiento registrado. Inmutable: si estaba mal, se ve; no se reescribe en silencio.

    Para el efectivo (`DEPOSIT`/`WITHDRAWAL`) no hay símbolo: el importe va en `quantity` y el
    precio unitario es 1. Para compras y ventas, `quantity` es siempre positiva — el sentido lo da
    el tipo, nunca el signo.
    """

    timestamp: datetime
    type: ActivityType
    symbol: str | None
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal = CERO
    """Comisión de ESTA operación. Forma parte del coste: es lo que de verdad pagaste."""
    source: str = FUENTE_MANUAL
    """De dónde vino: `manual`, `csv:<fichero>`, `ledger:<modo>:<referencia>`, `panel`..."""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                "la fecha del movimiento necesita zona horaria: sin ella, el orden entre "
                "movimientos dependeria de donde se lea"
            )
        for nombre, valor in (
            ("la cantidad", self.quantity),
            ("el precio", self.unit_price),
            ("la comision", self.fee),
        ):
            if not valor.is_finite():
                raise ValueError(f"{nombre} no es un numero finito: {valor}")
        if self.quantity <= 0:
            raise ValueError(
                f"cantidad no positiva: {self.quantity}. El sentido lo da el tipo "
                "(buy/sell, deposit/withdrawal), no el signo"
            )
        if self.fee < 0:
            raise ValueError(f"una comision negativa ({self.fee}) seria un ingreso disfrazado")

        if self.type.is_cash:
            if self.symbol is not None:
                raise ValueError(
                    f"un movimiento de efectivo ({self.type.value}) no lleva simbolo "
                    f"(recibido {self.symbol!r}): el importe va en la cantidad"
                )
            if self.unit_price != UNO:
                raise ValueError(
                    f"el efectivo va a precio 1 (recibido {self.unit_price}): "
                    "el importe es la cantidad"
                )
            if self.fee != 0:
                raise ValueError(
                    "un movimiento de efectivo no lleva comision: registra el importe neto que "
                    "entro o salio de verdad"
                )
            return

        if self.symbol is None or not self.symbol.strip():
            raise ValueError(f"una operacion {self.type.value} necesita simbolo")
        if self.unit_price <= 0:
            raise ValueError(
                f"precio no positivo en {self.symbol}: {self.unit_price}. "
                "Registra el precio que de verdad se pago o cobro"
            )

    @property
    def activity_id(self) -> str:
        """Identificador derivado del CONTENIDO, no de un contador ni del origen.

        Así un doble-import no puede duplicar una posición sin que nadie lo note: el mismo
        movimiento produce el mismo identificador, venga del CSV, del registro de órdenes o
        tecleado a mano. Las cifras se normalizan (`10` y `10.0` son la misma cantidad) y la fecha
        se lleva a UTC (la misma hora escrita en otra zona es el mismo instante).
        """
        material = "|".join(
            (
                self.timestamp.astimezone(UTC).isoformat(),
                self.type.value,
                self.symbol or "",
                como_texto(self.quantity),
                como_texto(self.unit_price),
                como_texto(self.fee),
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()[:LONGITUD_ID]

    @property
    def gross(self) -> Decimal:
        """Importe bruto: cantidad por precio, sin comisión."""
        return self.quantity * self.unit_price

    @property
    def cash_effect(self) -> Decimal:
        """Cuánto cambia el efectivo con este movimiento, con su signo y la comisión dentro."""
        if self.type is ActivityType.BUY:
            return -(self.gross + self.fee)
        if self.type is ActivityType.SELL:
            return self.gross - self.fee
        if self.type is ActivityType.DEPOSIT:
            return self.quantity
        return -self.quantity


@dataclass(frozen=True, slots=True)
class OpenPosition:
    """Lo que tienes de un activo ahora. Su P&L es una VALORACIÓN, no un hecho.

    `cost` es el coste de lo que queda, con las comisiones dentro (coste medio, modelo Portfolio
    Performance): vender una parte no cambia lo que pagaste por el resto. `invested_total` y
    `proceeds_total` son los totales del episodio entero —todo lo pagado y todo lo cobrado desde
    que se abrió— y son los que pasan a `ClosedTrade` cuando la cantidad llega a 0.
    """

    symbol: str
    quantity: Decimal
    cost: Decimal
    opened_at: datetime
    invested_total: Decimal
    proceeds_total: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(
                f"una posicion abierta de {self.symbol} necesita cantidad positiva: {self.quantity}"
            )
        if self.cost < 0:
            raise ValueError(f"coste negativo en {self.symbol}: {self.cost}")
        if self.opened_at.tzinfo is None:
            raise ValueError("la fecha de apertura necesita zona horaria")

    @property
    def avg_cost(self) -> Decimal:
        """Coste medio por unidad, comisiones incluidas."""
        return self.cost / self.quantity

    def value_at(self, price: Decimal) -> Decimal:
        """Valor a ese precio. Quien lo muestre debe poner al lado la fecha del precio."""
        return self.quantity * price

    def unrealized_at(self, price: Decimal) -> Decimal:
        """P&L no realizado a ese precio: valor menos lo que costó lo que queda."""
        return self.value_at(price) - self.cost

    @property
    def realized_pnl(self) -> Decimal:
        """Lo ya realizado con ventas PARCIALES de este episodio: eso sí es un hecho.

        Lo cobrado menos el coste de lo vendido. Es 0 si no se ha vendido nada. Sin esto, la
        ganancia de una venta parcial desaparecería de las cifras hasta cerrar la posición.
        """
        return self.proceeds_total - (self.invested_total - self.cost)


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """Un episodio cerrado: la cantidad llegó a 0. Su P&L es un HECHO que ya no cambia."""

    symbol: str
    opened_at: datetime
    closed_at: datetime
    invested_total: Decimal
    """Todo lo pagado en el episodio, comisiones incluidas."""
    proceeds_total: Decimal
    """Todo lo cobrado en el episodio, con las comisiones ya descontadas."""

    @property
    def realized_pnl(self) -> Decimal:
        return self.proceeds_total - self.invested_total

    @property
    def holding_days(self) -> int:
        """Días entre la primera compra del episodio y la venta que lo cerró."""
        return (self.closed_at - self.opened_at).days
