"""Inicio: cómo va tu dinero y qué tienes que hacer (docs/panel-v2.md, 4.1).

Una cifra grande con su fecha (`portfolio.valoracion` sobre la cartera del modo activo), tu plan
por partes, cuántas cosas tocan hoy (`plan.servicio`, lo mismo que `GET /api/plan/hoy`), los avisos
que haya y el mercado en una línea con nombres llanos. Solo se lee; nada se envía.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter

from invest_ll.api.modo import almacen_del_modo, cartera_del_modo, modo_efectivo
from invest_ll.api.schemas_v2 import Inicio, MiniMercado, ParteResumen, Patrimonio
from invest_ll.errors import InvestLLError
from invest_ll.estrategias import datos
from invest_ll.estrategias.catalogo import ficha
from invest_ll.nombres import nombre_llano
from invest_ll.plan import almacen, servicio
from invest_ll.plan.hoy import AVISO_USDT
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.triggers import TriggerStore
from invest_ll.portfolio.valoracion import valorar

if TYPE_CHECKING:  # pragma: no cover
    from datetime import date

    from invest_ll.portfolio.derive import Portfolio
    from invest_ll.portfolio.models import Activity

router = APIRouter()

MERCADO_EN_UNA_LINEA: Final = ("BTC/USDT", "SPY", "GLD", "IEF")


def _precio(simbolo: str) -> tuple[Decimal, date] | None:
    visto = datos.cierre(simbolo)
    return None if visto is None else (visto.precio, visto.fecha)


def _mercado() -> list[MiniMercado]:
    filas: list[MiniMercado] = []
    for simbolo in MERCADO_EN_UNA_LINEA:
        visto = datos.variacion_del_mes(simbolo)
        if visto is None:
            continue
        filas.append(
            MiniMercado(
                nombre=nombre_llano(simbolo),
                symbol=simbolo,
                precio=visto.precio,
                var_1m=visto.var_1m,
                fecha=visto.fecha,
            )
        )
    return filas


def _partes(plan: almacen.Plan, cartera: Portfolio | None) -> list[ParteResumen]:
    partes: list[ParteResumen] = []
    for parte in plan.partes:
        f = ficha(parte.estrategia)
        if f is None:  # pragma: no cover - validado al guardar
            continue
        valor: Decimal | None = None
        puesto = Decimal(0)
        if cartera is not None:
            v = valorar(cartera, _precio, solo=f.posee, con_efectivo=False)
            valor, puesto = v.valor, v.puesto
        partes.append(
            ParteResumen(
                estrategia=f.clave, nombre=f.nombre, mercado=f.mercado, valor=valor, puesto=puesto
            )
        )
    return partes


@router.get("/inicio", tags=["inicio"])
def inicio() -> Inicio:
    """Tu dinero hoy (cartera del modo activo), el plan resumido, acciones pendientes y avisos."""
    efectivo = modo_efectivo()
    avisos: list[str] = [] if efectivo.aviso is None else [efectivo.aviso]
    actividades: list[Activity] = []
    cartera: Portfolio | None = None
    try:
        actividades = almacen_del_modo(efectivo.modo).activities()
        cartera = derive_portfolio(actividades)
    except InvestLLError as error:
        avisos.append(f"Tu registro de movimientos tiene un problema: {error}")

    if cartera is not None:
        v = valorar(cartera, _precio)
        sin_precio = [
            nombre_llano(p.symbol) for p in cartera.open_positions if _precio(p.symbol) is None
        ]
        if sin_precio:
            avisos.append(
                "Falta el precio de " + ", ".join(sin_precio) + ": la cifra no se puede calcular "
                "entera. Actualiza los datos."
            )
        patrimonio = Patrimonio(
            valor=v.valor,
            puesto=v.puesto,
            ganancia=v.ganancia,
            ganancia_pct=v.ganancia_pct,
            realizado=v.realizado,
            fecha_precios=v.fecha_precios,
            incompleto=v.incompleto,
            cartera=cartera_del_modo(efectivo.modo),
        )
    else:
        patrimonio = Patrimonio(
            valor=None,
            puesto=Decimal(0),
            ganancia=None,
            ganancia_pct=None,
            realizado=Decimal(0),
            fecha_precios=None,
            incompleto=True,
            cartera=cartera_del_modo(efectivo.modo),
        )

    pausa = TriggerStore().halted()
    if pausa is not None:
        avisos.append(f"Las compras están en pausa: {pausa}.")

    try:
        plan = almacen.PlanStore().leer()
    except almacen.PlanIlegibleError as error:
        # Inicio es lo primero que se ve: un plan estropeado se dice aquí, no tumba la pantalla.
        plan = None
        avisos.append(str(error))
    pendientes = 0
    proxima: date | None = None
    partes: list[ParteResumen] | None = None
    if plan is not None:
        partes = _partes(plan, cartera)
        if cartera is not None:
            resultado = servicio.calcular_hoy(
                plan, actividades, hoy=servicio.hoy_local(), pausa=pausa
            )
            pendientes = len(resultado.acciones)
            proxima = resultado.proxima_fecha
            # Lo de la pausa ya esta arriba, y lo de tener USDT es para el momento de operar.
            avisos.extend(
                a
                for a in resultado.avisos
                if a != AVISO_USDT and not a.startswith("Las compras están en pausa")
            )

    return Inicio(
        patrimonio=patrimonio,
        hay_movimientos=bool(actividades),
        plan=partes,
        acciones_pendientes=pendientes,
        proxima_fecha=proxima,
        avisos=list(dict.fromkeys(avisos)),
        mercado=_mercado(),
    )
