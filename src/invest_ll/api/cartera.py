"""Pestaña Mi cartera: qué tienes (derivado del ledger) y qué mandaste al mercado.

Viven separadas a propósito: la cartera dice **qué tienes**, y las órdenes **qué mandaste**. Una
orden rechazada o de estado desconocido no cambia lo que tienes, pero es justo lo que hay que poder
mirar cuando algo ha ido mal.

Registrar un movimiento es contabilidad: escribe en el ledger y no envía nada. La única ruta que
puede mover dinero es `POST /api/ordenes`, con los mismos cerrojos que `invest-ll-execute`
(`dashboard/ordenes.py`, usado tal cual): en simulación responde 403 sin construir ningún broker,
y en cualquier otro modo exige la cantidad tecleada.

**Cada modo tiene su cartera** (`api.modo`): la de pruebas (`portfolio-pruebas/`) es dinero
ficticio con precios que no son los del mercado, y no se mezcla con la real (`portfolio/`, la que
se ve también en simulación). Mirar, anotar y lo que ejecuta `POST /api/ordenes` van a la cartera
del modo efectivo; lo ejecutado pasa solo, con las reglas de `portfolio.from_orders` (sin comisión
conocida no entra, y se dice).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter

from invest_ll import llano
from invest_ll.api.errores import del_dominio, invalido, prohibido
from invest_ll.api.modo import almacen_activo, almacen_del_modo, cartera_del_modo, modo_efectivo
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
from invest_ll.api.schemas_v2 import Movimiento, Movimientos
from invest_ll.dashboard.ordenes import enviar_orden, motivo_para_no_enviar
from invest_ll.errors import InvestLLError
from invest_ll.estrategias.datos import cierre
from invest_ll.live.broker import OrderStatus, Side
from invest_ll.live.factory import construir_broker
from invest_ll.live.ledger import ExecutionLedger
from invest_ll.nombres import nombre_llano
from invest_ll.portfolio.derive import aviso_de_efectivo, derive_portfolio
from invest_ll.portfolio.from_orders import importar_a_cartera
from invest_ll.portfolio.models import Activity, ActivityType

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.live.broker import Broker, OrderResult
    from invest_ll.live.mode import OperatingMode
    from invest_ll.portfolio.derive import Portfolio

router = APIRouter()

CERO = Decimal(0)
FUENTE_PANEL = "panel"
TipoMovimiento = Literal["compra", "venta", "ingreso", "retirada"]
TIPO_LLANO: dict[ActivityType, TipoMovimiento] = {
    ActivityType.BUY: "compra",
    ActivityType.SELL: "venta",
    ActivityType.DEPOSIT: "ingreso",
    ActivityType.WITHDRAWAL: "retirada",
}


def broker_para(modo: OperatingMode) -> Broker:
    """El broker del modo. Fuera de simulación habla con el exchange: los tests lo sustituyen."""
    return construir_broker(modo)


# -- Mi cartera --------------------------------------------------------------------------------


@router.get("/cartera", tags=["cartera"])
def cartera() -> Cartera:
    """La cartera derivada del ledger, valorada con el último cierre y SU fecha."""
    try:
        derivada = derive_portfolio(almacen_activo().activities())
    except InvestLLError as error:
        return Cartera(
            vacia=False,
            error=f"Tu registro de movimientos cuenta una historia imposible: {error}",
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
        ultimo = cierre(p.symbol)
        if ultimo is None:
            precio, fecha = None, None
            valor_total = None  # sin el precio de una, el total seria inventado
        else:
            precio, fecha = ultimo.precio, ultimo.fecha
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
                precio_fecha=fecha,
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
        avisos=_avisos_en_llano(derivada),
        abiertas=abiertas,
        retiradas=retiradas,
        invertido_abiertas=derivada.invested_open,
        valor_total=valor_total,
        efectivo=derivada.cash,
        realizado_total=derivada.realized_pnl,
    )


def _avisos_en_llano(derivada: Portfolio) -> list[str]:
    """Los avisos de `derive` hablan a la terminal (cifras a la inglesa, un comando que teclear).

    En el panel, el del efectivo se cuenta en llano y con lo que se puede hacer desde él; lo
    demás pasa tal cual.
    """
    if derivada.efectivo_minimo is None:
        return list(derivada.warnings)
    cifra, cuando = derivada.efectivo_minimo
    del_efectivo = (
        "Has anotado compras por más dinero del que has anotado como ingresado: el "
        f"{llano.fecha_corta(cuando.date())} faltaban {llano.euros(-cifra)}. Lo que tienes y lo que "
        "vale está bien; solo el dinero sin invertir que calcula el panel no cuadra. Si quieres que "
        "cuadre, anota lo que ingresaste con «Anotar un movimiento» (con la fecha de las compras "
        "o una anterior)."
    )
    return [del_efectivo, *(a for a in derivada.warnings if a != aviso_de_efectivo(cifra, cuando))]


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
        identificador = almacen_activo().append(actividad)
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
        modo_efectivo().modo, cantidad=comprobacion.cantidad, escrito=comprobacion.escrito
    )
    return EstadoEnvio(puede=motivo is None, motivo=motivo)


@router.post("/ordenes", tags=["ordenes"])
def enviar(peticion: PeticionOrden) -> ResultadoOrden:
    """Envía UNA orden con la confirmación tecleada (`enviar_orden`). 403 en simulación."""
    # Lo ejecutado pasa solo a la cartera del modo. Si no puede pasar (sin comision conocida, por
    # ejemplo), la descripcion lo dice: la orden ya salio y eso no se deshace con un error.
    modo = modo_efectivo().modo
    motivo = motivo_para_no_enviar(modo, cantidad=peticion.cantidad, escrito=peticion.escrito)
    if not modo.sends_real_orders:
        # Ni siquiera se construye un broker: en simulacion no hay nada a lo que enviar.
        raise prohibido(motivo or "Modo simulacion: no se envia nada al exterior.")
    if motivo is not None:
        raise invalido(motivo)

    registro = ExecutionLedger()
    with del_dominio():
        resultado = enviar_orden(
            broker_para(modo),
            symbol=peticion.par,
            side=Side(peticion.lado),
            cantidad=peticion.cantidad,
            escrito=peticion.escrito,
            ahora=datetime.now(UTC),
            ledger=registro,
        )
    descripcion = resultado.describe()
    nota = _a_la_cartera(modo, resultado, registro)
    return ResultadoOrden(
        estado=resultado.status.value,
        descripcion=descripcion if nota is None else f"{descripcion} {nota}",
        necesita_atencion=resultado.needs_attention,
        modo=modo.name,
    )


def _a_la_cartera(
    modo: OperatingMode, resultado: OrderResult, registro: ExecutionLedger
) -> str | None:
    """Pasa lo ejecutado a la cartera del modo. Devuelve una nota si NO pudo pasar.

    Se importa la entrada tal como quedó en el registro (la última que coincide con este
    resultado), para que `invest-ll-portfolio import-ledger` la reconozca después y no la duplique.
    Nada de aquí puede lanzar: la orden ya salió, y un 500 haría creer que no.
    """
    if resultado.status not in (OrderStatus.FILLED, OrderStatus.PARTIAL):
        return None  # rechazada o desconocida: `describe()` ya dice que no hay nada que anotar
    try:
        entrada = next(e for e in reversed(registro.entries()) if e.result == resultado)
        importado = importar_a_cartera(
            [entrada], almacen_del_modo(modo), modos=frozenset({modo.name})
        )
    except (StopIteration, InvestLLError, ValueError, OSError) as error:
        return (
            f"No se ha podido anotar en tu cartera ({error}): anótala a mano o con "
            "invest-ll-portfolio import-ledger."
        )
    if importado.activities or importado.already_known:
        return None
    return f"No ha pasado a tu cartera: {importado.describe()} Anótala a mano con su comisión real."


@router.get("/cartera/movimientos", tags=["cartera"])
def movimientos() -> Movimientos:
    """El registro de la cartera del modo activo, legible y el más reciente primero."""
    modo = modo_efectivo().modo
    actividades = almacen_del_modo(modo).activities()
    return Movimientos(
        cartera=cartera_del_modo(modo),
        movimientos=[_movimiento(a) for a in reversed(actividades)],
    )


def _movimiento(a: Activity) -> Movimiento:
    efectivo = a.type.is_cash
    return Movimiento(
        id=a.activity_id,
        fecha=a.timestamp,
        tipo=TIPO_LLANO[a.type],
        activo=None if a.symbol is None else nombre_llano(a.symbol),
        simbolo=a.symbol,
        cantidad=a.quantity,
        precio=None if efectivo else a.unit_price,
        comision=a.fee,
        importe=a.quantity if efectivo else a.gross,
        origen=a.source,
    )
