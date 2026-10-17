"""Pestaña Mi cartera: qué tienes (derivado del ledger) y qué mandaste al mercado.

Viven separadas a propósito: la cartera dice **qué tienes**, y las órdenes **qué mandaste**. Una
orden rechazada o de estado desconocido no cambia lo que tienes, pero es justo lo que hay que poder
mirar cuando algo ha ido mal.

Registrar un movimiento es contabilidad: escribe en el ledger y no envía nada. La única ruta que
puede mover dinero es `POST /api/ordenes`, con los mismos cerrojos que `invest-ll-execute`
(`dashboard/ordenes.py`, usado tal cual): en simulación responde 403 sin construir ningún broker,
y en cualquier otro modo exige la cantidad tecleada.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from fastapi import APIRouter

from invest_ll.api.errores import del_dominio, invalido, prohibido
from invest_ll.api.schemas import (
    Cartera,
    ComprobacionEnvio,
    EstadoEnvio,
    FilaOrden,
    MovimientoRegistrado,
    NuevoMovimiento,
    OrdenesEnviadas,
    PeticionOrden,
    PosicionAbierta,
    PosicionRetirada,
    ResultadoOrden,
)
from invest_ll.dashboard.ordenes import enviar_orden, motivo_para_no_enviar
from invest_ll.errors import InvestLLError
from invest_ll.live.broker import Side
from invest_ll.live.factory import construir_broker
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.live.mode import resolve_mode
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.quotes import ultimo_cierre
from invest_ll.portfolio.store import ActivityStore

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.broker import Broker
    from invest_ll.live.mode import OperatingMode

router = APIRouter()

CERO = Decimal(0)
FUENTE_PANEL = "panel"


def broker_para(modo: OperatingMode) -> Broker:
    """El broker del modo. Fuera de simulación habla con el exchange: los tests lo sustituyen."""
    return construir_broker(modo)


# -- Mi cartera --------------------------------------------------------------------------------


@router.get("/cartera", tags=["cartera"])
def cartera() -> Cartera:
    """La cartera derivada del ledger, valorada con el último cierre y SU fecha."""
    try:
        derivada = derive_portfolio(ActivityStore().activities())
    except InvestLLError as error:
        return Cartera(
            vacia=False,
            error=f"El ledger cuenta una historia imposible: {error}",
            avisos=[],
            abiertas=[],
            retiradas=[],
            invertido_abiertas=CERO,
            valor_total=None,
            efectivo=CERO,
            realizado_total=CERO,
        )

    abiertas: list[PosicionAbierta] = []
    valor_total: Decimal | None = CERO
    for p in derivada.open_positions:
        cierre = ultimo_cierre(p.symbol)
        if cierre is None:
            precio, fecha = None, None
            valor_total = None  # sin el precio de una, el total seria inventado
        else:
            precio, fecha = cierre
            if valor_total is not None:
                valor_total += p.value_at(precio)
        abiertas.append(
            PosicionAbierta(
                activo=p.symbol,
                cantidad=p.quantity,
                coste_medio=p.avg_cost,
                invertido=p.cost,
                abierta=p.opened_at,
                precio=precio,
                precio_fecha=fecha.date() if fecha is not None else None,
                valor=p.value_at(precio) if precio is not None else None,
                pnl_no_realizado=p.unrealized_at(precio) if precio is not None else None,
            )
        )

    retiradas = [
        PosicionRetirada(
            activo=t.symbol,
            abierta=t.opened_at.date(),
            retirada=t.closed_at.date(),
            dias=t.holding_days,
            invertido=t.invested_total,
            recuperado=t.proceeds_total,
            pnl_realizado=t.realized_pnl,
        )
        for t in derivada.closed_trades
    ]

    return Cartera(
        vacia=not derivada.open_positions and not derivada.closed_trades,
        error=None,
        avisos=list(derivada.warnings),
        abiertas=abiertas,
        retiradas=retiradas,
        invertido_abiertas=derivada.invested_open,
        valor_total=valor_total,
        efectivo=derivada.cash,
        realizado_total=derivada.realized_pnl,
    )


def _actividad(movimiento: NuevoMovimiento) -> Activity:
    """El movimiento tecleado, como lo construía el formulario del panel."""
    momento = datetime(
        movimiento.fecha.year, movimiento.fecha.month, movimiento.fecha.day, tzinfo=UTC
    )
    if movimiento.tipo in ("compra", "venta"):
        simbolo = (movimiento.simbolo or "").strip().upper()
        if not simbolo:
            raise invalido(f"No registrado: una {movimiento.tipo} necesita el activo")
        if movimiento.precio is None:
            raise invalido(f"No registrado: una {movimiento.tipo} necesita el precio unitario")
        with del_dominio("No registrado: "):
            return Activity(
                timestamp=momento,
                type=ActivityType.BUY if movimiento.tipo == "compra" else ActivityType.SELL,
                symbol=simbolo,
                quantity=movimiento.cantidad,
                unit_price=movimiento.precio,
                fee=movimiento.comision,
                source=FUENTE_PANEL,
            )
    # Efectivo: sin simbolo, a precio 1 y sin comision, como hacia el formulario del panel.
    with del_dominio("No registrado: "):
        return Activity(
            timestamp=momento,
            type=ActivityType.DEPOSIT if movimiento.tipo == "deposito" else ActivityType.WITHDRAWAL,
            symbol=None,
            quantity=movimiento.cantidad,
            unit_price=Decimal(1),
            source=FUENTE_PANEL,
        )


@router.post("/cartera/movimientos", tags=["cartera"], status_code=201)
def registrar_movimiento(movimiento: NuevoMovimiento) -> MovimientoRegistrado:
    """Escribe un movimiento en el ledger (fuente 'panel'). No envía ninguna orden."""
    actividad = _actividad(movimiento)
    with del_dominio("No registrado: "):
        identificador = ActivityStore().append(actividad)
    return MovimientoRegistrado(activity_id=identificador)


# -- Ordenes -----------------------------------------------------------------------------------


@router.get("/ordenes", tags=["ordenes"])
def ordenes() -> OrdenesEnviadas:
    """Lo que de verdad salió al mercado, con el modo de cada orden a la vista."""
    registro = ExecutionLedger()
    entradas = registro.entries()
    filas = [
        FilaOrden(
            cuando=e.result.executed_at or e.recorded_at,
            modo=e.mode_name,
            activo=e.result.request.symbol,
            lado=e.result.request.side.value,
            pedida=e.result.request.quantity,
            ejecutada=e.result.filled_quantity,
            precio=e.result.fill_price or None,
            comision=e.result.commission,
            estado=e.result.status.value,
            referencia=e.result.broker_reference or "",
        )
        for e in reversed(entradas)
    ]
    return OrdenesEnviadas(
        filas=filas,
        total=len(entradas),
        reales=sum(1 for e in entradas if e.was_real_money),
        atencion=[e.result.describe() for e in entradas if e.result.needs_attention],
        sin_comision=sum(
            1 for e in entradas if e.result.commission is None and e.result.filled_quantity > 0
        ),
        registro=registro.path.as_posix(),
    )


@router.post("/ordenes/comprobar", tags=["ordenes"])
def comprobar_envio(comprobacion: ComprobacionEnvio) -> EstadoEnvio:
    """Si con el modo actual y lo tecleado se podría enviar (`motivo_para_no_enviar`)."""
    motivo = motivo_para_no_enviar(
        resolve_mode(), cantidad=comprobacion.cantidad, escrito=comprobacion.escrito
    )
    return EstadoEnvio(puede=motivo is None, motivo=motivo)


@router.post("/ordenes", tags=["ordenes"])
def enviar(peticion: PeticionOrden) -> ResultadoOrden:
    """Envía UNA orden con la confirmación tecleada (`enviar_orden`). 403 en simulación."""
    modo = resolve_mode()
    motivo = motivo_para_no_enviar(modo, cantidad=peticion.cantidad, escrito=peticion.escrito)
    if not modo.sends_real_orders:
        # Ni siquiera se construye un broker: en simulacion no hay nada a lo que enviar.
        raise prohibido(motivo or "Modo simulacion: no se envia nada al exterior.")
    if motivo is not None:
        raise invalido(motivo)

    with del_dominio():
        resultado = enviar_orden(
            broker_para(modo),
            symbol=peticion.par,
            side=Side(peticion.lado),
            cantidad=peticion.cantidad,
            escrito=peticion.escrito,
            ahora=datetime.now(UTC),
            ledger=ExecutionLedger(),
        )
    return ResultadoOrden(
        estado=resultado.status.value,
        descripcion=resultado.describe(),
        necesita_atencion=resultado.needs_attention,
        modo=modo.name,
    )
