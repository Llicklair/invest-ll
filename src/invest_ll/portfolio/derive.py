"""De los movimientos a la cartera: posiciones abiertas, episodios cerrados y efectivo.

Nada de lo que sale de aquí se guarda: se recalcula cada vez desde el ledger. Una cartera que se
pudiera editar sería una opinión; derivada, cualquiera puede rehacer la cuenta.

Dos reglas que no se negocian:

- **Vender lo que el ledger no registra FALLA**, con el número delante. Derivar una cantidad
  negativa sería un ledger incompleto con aspecto de cartera válida.
- **El efectivo se avisa, no se impone.** Comprar sin depósitos registrados no rompe nada: las
  posiciones siguen siendo fiables y el efectivo no, y el aviso dice exactamente eso.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.portfolio.models import (
    CERO,
    Activity,
    ActivityType,
    ClosedTrade,
    LedgerInconsistencyError,
    OpenPosition,
    como_texto,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Iterable


@dataclass(frozen=True, slots=True)
class Portfolio:
    """La cartera derivada. Abiertas = valoración; cerradas = hecho. No se suman nunca."""

    open_positions: tuple[OpenPosition, ...]
    closed_trades: tuple[ClosedTrade, ...]
    cash: Decimal
    """Efectivo DERIVADO de los movimientos. Si faltan depósitos por registrar, no es el real."""
    total_deposited: Decimal
    total_withdrawn: Decimal
    warnings: tuple[str, ...] = ()
    """Avisos sobre el efectivo: cuándo no se puede fiar de `cash`."""

    @property
    def realized_pnl(self) -> Decimal:
        """Todo el P&L realizado: episodios cerrados más ventas parciales de los abiertos.

        Las dos partes son hechos. Contar solo los episodios cerrados haría desaparecer la
        ganancia (o pérdida) de una venta parcial hasta el día en que se vendiera el resto.
        """
        cerrado = sum((t.realized_pnl for t in self.closed_trades), CERO)
        parcial = sum((p.realized_pnl for p in self.open_positions), CERO)
        return cerrado + parcial

    @property
    def invested_open(self) -> Decimal:
        """Lo que costó lo que sigue abierto, comisiones incluidas."""
        return sum((p.cost for p in self.open_positions), CERO)


@dataclass(slots=True)
class _Episodio:
    """Una posición mientras se recorre el ledger. Mutable solo aquí dentro."""

    symbol: str
    quantity: Decimal
    cost: Decimal
    opened_at: datetime
    invested: Decimal
    proceeds: Decimal


def derive_portfolio(activities: Iterable[Activity]) -> Portfolio:
    """Recorre los movimientos en orden temporal y deriva la cartera.

    Raises:
        LedgerInconsistencyError: si en algún momento se vende más de lo que el ledger registra.
    """
    # sorted es estable: ante la misma fecha manda el orden de escritura.
    ordenadas = sorted(activities, key=lambda a: a.timestamp)

    abiertas: dict[str, _Episodio] = {}
    cerradas: list[ClosedTrade] = []
    efectivo = CERO
    depositado = CERO
    retirado = CERO
    peor_efectivo: tuple[Decimal, datetime] | None = None

    for actividad in ordenadas:
        if actividad.type is ActivityType.DEPOSIT:
            depositado += actividad.quantity
        elif actividad.type is ActivityType.WITHDRAWAL:
            retirado += actividad.quantity
        elif actividad.type is ActivityType.BUY:
            _comprar(abiertas, actividad)
        else:
            cerrada = _vender(abiertas, actividad)
            if cerrada is not None:
                cerradas.append(cerrada)

        efectivo += actividad.cash_effect
        if efectivo < 0 and (peor_efectivo is None or efectivo < peor_efectivo[0]):
            peor_efectivo = (efectivo, actividad.timestamp)

    avisos: list[str] = []
    if peor_efectivo is not None:
        cifra, cuando = peor_efectivo
        avisos.append(
            f"El efectivo derivado llega a {cifra:,.2f} el {cuando.date()}: faltan depositos por "
            "registrar (o tienen fecha posterior a las compras). Las posiciones son fiables; "
            "el efectivo, no. Registralos con: invest-ll-portfolio cash deposit --amount ..."
        )

    return Portfolio(
        open_positions=tuple(
            OpenPosition(
                symbol=e.symbol,
                quantity=e.quantity,
                cost=e.cost,
                opened_at=e.opened_at,
                invested_total=e.invested,
                proceeds_total=e.proceeds,
            )
            for e in sorted(abiertas.values(), key=lambda e: e.symbol)
        ),
        closed_trades=tuple(cerradas),
        cash=efectivo,
        total_deposited=depositado,
        total_withdrawn=retirado,
        warnings=tuple(avisos),
    )


def _simbolo(actividad: Activity) -> str:
    if actividad.symbol is None:  # pragma: no cover - Activity ya lo impide al construirse
        raise LedgerInconsistencyError(f"una {actividad.type.value} sin simbolo")
    return actividad.symbol


def _comprar(abiertas: dict[str, _Episodio], compra: Activity) -> None:
    simbolo = _simbolo(compra)
    pagado = compra.gross + compra.fee
    episodio = abiertas.get(simbolo)
    if episodio is None:
        # Recomprar tras cerrar abre un episodio NUEVO: no hereda costes del anterior.
        abiertas[simbolo] = _Episodio(
            symbol=simbolo,
            quantity=compra.quantity,
            cost=pagado,
            opened_at=compra.timestamp,
            invested=pagado,
            proceeds=CERO,
        )
        return
    episodio.quantity += compra.quantity
    episodio.cost += pagado
    episodio.invested += pagado


def _vender(abiertas: dict[str, _Episodio], venta: Activity) -> ClosedTrade | None:
    """Aplica una venta. Devuelve el episodio cerrado si la cantidad llega a 0."""
    simbolo = _simbolo(venta)
    episodio = abiertas.get(simbolo)
    disponible = episodio.quantity if episodio is not None else CERO
    if episodio is None or venta.quantity > disponible:
        raise LedgerInconsistencyError(
            f"venta de {como_texto(venta.quantity)} {simbolo} el {venta.timestamp.date()}, pero el "
            f"ledger solo registra {como_texto(disponible)} en ese momento. Falta alguna compra, o "
            "la venta esta mal anotada: no se deriva una cartera con cantidades negativas."
        )

    episodio.proceeds += venta.gross - venta.fee
    restante = episodio.quantity - venta.quantity
    if restante == 0:
        del abiertas[simbolo]
        return ClosedTrade(
            symbol=simbolo,
            opened_at=episodio.opened_at,
            closed_at=venta.timestamp,
            invested_total=episodio.invested,
            proceeds_total=episodio.proceeds,
        )

    # Coste medio: vender una parte no cambia lo que pagaste por lo que queda.
    episodio.cost = episodio.cost * restante / episodio.quantity
    episodio.quantity = restante
    return None
