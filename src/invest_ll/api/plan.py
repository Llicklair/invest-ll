"""Tu plan y qué toca hacer hoy (docs/panel-v2.md, 4.2 paso 3, 4.3 y 7).

Las rutas traducen: el plan se guarda con `plan.almacen` (en `plan/plan.json`, fuera de git), lo
que toca hoy lo calcula `plan.hoy` con lo que junta `plan.servicio`, y todo mira la cartera del
modo activo (`api.modo`). **Nada de aquí envía órdenes**: las de Binance van por
`POST /api/ordenes`, con la cantidad tecleada.

Anotar una compra del bróker (`hecho`) guarda lo que pagaste —importe y comisión, exactos— en
unidades del fondo de EE.UU. de referencia: desde España se compra la versión europea (UCITS), que
cotiza a otro precio, y la cartera se valora con el precio del fondo de referencia. Guardar la
cantidad y el precio del fondo europeo junto al precio del de EE.UU. haría que la cartera valiera
lo que no vale (con el oro, varias veces más). Lo pagado no cambia; las unidades sí. Para que eso
no esconda lo que hiciste, el movimiento lleva una `nota` en llano con tus participaciones y tu
precio, y la cartera lo marca (`es_referencia`): se enseñan importes, no unidades.

Una venta del bróker (`lado="sell"`, cuando la estrategia sale de un fondo o le sobra) se anota
igual, al revés: lo que cobraste entre el precio de referencia de ese día son las unidades que
salen (`plan.hoy.venta_en_unidades`), nunca más de las que el plan compró. Lo cobrado queda como
dinero sin invertir de tu parte de bolsa hasta que lo vuelvas a invertir con el plan
(`plan.hoy.EnElBroker.libre`): Inicio y Cartera lo cuentan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter

from invest_ll import llano
from invest_ll.api.errores import del_dominio, invalido, no_encontrado
from invest_ll.api.modo import almacen_activo, almacen_del_broker, modo_efectivo
from invest_ll.api.schemas import MovimientoRegistrado
from invest_ll.api.schemas_v2 import (
    Accion,
    AccionHecha,
    Hoy,
    NuevoPlan,
    ParteDelPlan,
    PlanGuardado,
)
from invest_ll.api.schemas_v2 import Plan as PlanApi
from invest_ll.estrategias.catalogo import ficha
from invest_ll.live.modo_panel import modo_del_panel
from invest_ll.nombres import moneda_de
from invest_ll.plan import almacen, servicio
from invest_ll.plan.hoy import (
    FUENTE_PLAN,
    UNIDADES_DE_REFERENCIA,
    VentaAnotada,
    VentaImposibleError,
    venta_en_unidades,
)
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.models import Activity, ActivityType
from invest_ll.portfolio.triggers import TriggerStore

if TYPE_CHECKING:  # pragma: no cover
    from invest_ll.plan.hoy import Accion as AccionCalculada
    from invest_ll.plan.hoy import Resultado

router = APIRouter()

SIN_PLAN: Final = "Todavía no tienes un plan. Empieza en Estrategias: cinco preguntas, sin jerga."
CENTESIMAS: Final = Decimal("0.01")
DIEZMILESIMAS: Final = Decimal("0.0001")


def _plan_api(plan: almacen.Plan) -> PlanApi:
    return PlanApi(
        partes=[
            ParteDelPlan(estrategia=p.estrategia, inicial=p.inicial, mensual=p.mensual)
            for p in plan.partes
        ],
        dia_del_mes=plan.dia_del_mes,
        creado=plan.creado,
        actualizado=plan.actualizado,
    )


def _leer() -> almacen.Plan | None:
    with del_dominio():
        return almacen.PlanStore().leer()


@router.get("/plan", tags=["plan"])
def ver_plan() -> PlanGuardado:
    plan = _leer()
    return PlanGuardado(plan=None if plan is None else _plan_api(plan))


@router.put("/plan", tags=["plan"])
def guardar_plan(plan: NuevoPlan) -> PlanGuardado:
    """422 si hay dos estrategias del mismo mercado o una clave desconocida o de laboratorio."""
    partes = tuple(
        almacen.Parte(estrategia=p.estrategia, inicial=p.inicial, mensual=p.mensual)
        for p in plan.partes
    )
    with del_dominio():
        almacen.validar(partes, plan.dia_del_mes, ficha)
    previo = _leer()
    ahora = datetime.now(UTC)
    guardado = almacen.Plan(
        partes=partes,
        dia_del_mes=plan.dia_del_mes,
        # Reemplazar no reinicia la cuenta de aportaciones vencidas: se conserva la creación.
        creado=ahora if previo is None else previo.creado,
        actualizado=ahora,
    )
    with del_dominio():
        almacen.PlanStore().guardar(guardado)
    return PlanGuardado(plan=_plan_api(guardado))


@router.delete("/plan", tags=["plan"], status_code=204)
def borrar_plan() -> None:
    """404 si no había plan."""
    if not almacen.PlanStore().borrar():
        raise no_encontrado("no hay ningún plan guardado")


def _calcular(plan: almacen.Plan) -> Resultado:
    with del_dominio():
        actividades = almacen_activo().activities()
        del_broker = almacen_del_broker().activities()
    return servicio.calcular_hoy(
        plan,
        actividades,
        hoy=servicio.hoy_local(),
        pausa=TriggerStore().halted(),
        actividades_bolsa=del_broker,
    )


def _accion(a: AccionCalculada) -> Accion:
    return Accion(
        id=a.id,
        donde=a.donde,
        estrategia=a.estrategia,
        titulo=a.titulo,
        explicacion=a.explicacion,
        activo=a.activo,
        simbolo=a.simbolo,
        par=a.par,
        lado=a.lado,
        cantidad=a.cantidad,
        importe=a.importe,
        moneda=a.moneda,
        precio_ref=a.precio_ref,
        precio_ref_moneda=a.precio_ref_moneda,
        referencia=a.referencia,
        precio_fecha=a.precio_fecha,
        equivalente=a.equivalente,
    )


@router.get("/plan/hoy", tags=["plan"])
def hoy() -> Hoy:
    """Qué toca hacer hoy según el plan y la cartera del modo activo. No envía nada."""
    efectivo = modo_efectivo()
    modo = modo_del_panel(efectivo.modo)
    plan = _leer()
    if plan is None:
        return Hoy(
            sin_plan=True, modo=modo, acciones=[], resumen=SIN_PLAN, proxima_fecha=None, avisos=[]
        )
    resultado = _calcular(plan)
    avisos = list(resultado.avisos)
    if efectivo.aviso is not None:
        avisos.insert(0, efectivo.aviso)
    return Hoy(
        sin_plan=False,
        modo=modo,
        acciones=[_accion(a) for a in resultado.acciones],
        resumen=resultado.resumen,
        proxima_fecha=resultado.proxima_fecha,
        avisos=avisos,
    )


def nota_de_referencia(
    hecha: AccionHecha, accion: AccionCalculada, unidades: Decimal, referencia: Decimal
) -> str:
    """Lo que de verdad compraste y cómo queda anotado, para que la cartera no lo esconda.

    "Compraste 5,437 participaciones a 650 € en tu bróker; se anota como 4,63 de SPY (el fondo
    de EE.UU. de referencia) a 763,25 $ para poder valorarlo."
    """
    anotadas = unidades.quantize(CENTESIMAS if unidades >= 1 else DIEZMILESIMAS, ROUND_HALF_UP)
    return (
        f"Compraste {llano.cantidad(hecha.cantidad)} participaciones a "
        f"{llano.dinero(hecha.precio, accion.moneda)} en tu bróker; se anota como "
        f"{llano.cantidad(anotadas)} de {accion.simbolo} (el fondo de EE.UU. de referencia) a "
        f"{llano.dinero(referencia, moneda_de(accion.simbolo))} para poder valorarlo."
    )


def nota_de_venta(
    hecha: AccionHecha, accion: AccionCalculada, venta: VentaAnotada, referencia: Decimal
) -> str:
    """Lo que de verdad vendiste y cómo queda anotado.

    "Vendiste 3 participaciones a 210 € en tu bróker; se anota como 0,83 de EEM (el fondo de
    EE.UU. de referencia) a 45,10 $ para poder valorarlo."
    """
    que = (
        f"Vendiste {llano.cantidad(hecha.cantidad)} participaciones a "
        f"{llano.dinero(hecha.precio, accion.moneda)} en tu bróker; "
    )
    anotadas = venta.unidades.quantize(
        CENTESIMAS if venta.unidades >= 1 else DIEZMILESIMAS, ROUND_HALF_UP
    )
    if venta.todo:
        return (
            f"{que}se anota como la venta de todo lo que tenías de {accion.simbolo} con tu plan "
            f"({llano.cantidad(anotadas)}, el fondo de EE.UU. de referencia), por lo que cobraste."
        )
    return (
        f"{que}se anota como {llano.cantidad(anotadas)} de {accion.simbolo} (el fondo de EE.UU. "
        f"de referencia) a {llano.dinero(referencia, moneda_de(accion.simbolo))} para poder "
        "valorarlo."
    )


def _venta(plan: almacen.Plan, accion: AccionCalculada, hecha: AccionHecha) -> Activity:
    """La venta del bróker en unidades del fondo de referencia (`plan.hoy.venta_en_unidades`)."""
    cobrado = hecha.cantidad * hecha.precio
    referencia = servicio.precio_de_referencia(accion.simbolo, hecha.fecha, accion.precio_ref)
    if referencia is None or referencia <= 0:
        raise invalido(
            f"No hay precio de referencia de {accion.activo} para esa fecha: descarga los datos "
            "de los fondos (uv run invest-ll-quant download --etf)."
        )
    with del_dominio("No registrado: "):
        actividades = almacen_del_broker().activities()
    tenido = servicio.lo_del_broker(plan, actividades, hasta=hecha.fecha)
    tienes = tenido.unidades.get(accion.simbolo.upper(), Decimal(0))
    try:
        venta = venta_en_unidades(
            cobrado, referencia, tienes, sale_del_todo=accion.todo, nombre=accion.activo
        )
    except VentaImposibleError as error:
        raise invalido(str(error)) from error
    with del_dominio("No registrado: "):
        actividad = Activity(
            timestamp=datetime(hecha.fecha.year, hecha.fecha.month, hecha.fecha.day, tzinfo=UTC),
            type=ActivityType.SELL,
            symbol=accion.simbolo,
            quantity=venta.unidades,
            unit_price=venta.precio,
            fee=hecha.comision,
            source=FUENTE_PLAN,
            nota=nota_de_venta(hecha, accion, venta, referencia),
        )
        # Que la historia siga siendo posible: una venta fechada antes de las compras que vende
        # dejaría el registro sin poder derivarse (y todo el panel con él).
        derive_portfolio([*actividades, actividad])
    return actividad


@router.post("/plan/hoy/{accion_id}/hecho", tags=["plan"], status_code=201)
def hecho(accion_id: str, hecha: AccionHecha) -> MovimientoRegistrado:
    """Anota en tu registro una compra o una venta hecha en tu bróker (solo `donde=broker`)."""
    plan = _leer()
    if plan is None:
        raise no_encontrado("no hay ningún plan guardado")
    accion = next((a for a in _calcular(plan).acciones if a.id == accion_id), None)
    if accion is None:
        raise no_encontrado(
            f"la acción {accion_id!r} no está entre lo que toca hoy: puede que ya la anotaras"
        )
    if accion.donde != "broker":
        raise invalido(
            "Las órdenes de Binance no se anotan a mano: se envían con su confirmación y pasan "
            "solas a tu cartera."
        )
    hoy_ = servicio.hoy_local()
    venta = accion.lado == "sell"
    if hecha.fecha > hoy_:
        raise invalido(
            f"La fecha de la {'venta' if venta else 'compra'} no puede ser posterior a hoy."
        )
    if venta:
        actividad = _venta(plan, accion, hecha)
        with del_dominio("No registrado: "):
            # A la cartera real en cualquier modo, como las compras.
            identificador = almacen_del_broker().append(actividad)
        return MovimientoRegistrado(activity_id=identificador)
    if accion.periodo is not None and hecha.fecha < accion.periodo:
        raise invalido(
            f"Esta compra es de la aportación del {accion.periodo.isoformat()}: una compra de "
            "antes de esa fecha no es de esta aportación. Anótala como movimiento normal."
        )

    pagado = hecha.cantidad * hecha.precio
    referencia = servicio.precio_de_referencia(accion.simbolo, hecha.fecha, accion.precio_ref)
    if referencia is None or referencia <= 0:
        raise invalido(
            f"No hay precio de referencia de {accion.activo} para esa fecha: descarga los datos "
            "de los fondos (uv run invest-ll-quant download --etf)."
        )
    unidades = (pagado / referencia).quantize(UNIDADES_DE_REFERENCIA, ROUND_HALF_UP)
    with del_dominio("No registrado: "):
        actividad = Activity(
            timestamp=datetime(hecha.fecha.year, hecha.fecha.month, hecha.fecha.day, tzinfo=UTC),
            type=ActivityType.BUY,
            symbol=accion.simbolo,
            quantity=unidades,
            unit_price=referencia,
            fee=hecha.comision,
            source=FUENTE_PLAN,
            nota=nota_de_referencia(hecha, accion, unidades, referencia),
        )
        # A la cartera real en cualquier modo: lo del bróker nunca es dinero ficticio.
        identificador = almacen_del_broker().append(actividad)
    return MovimientoRegistrado(activity_id=identificador)
