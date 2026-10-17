"""Inicio: cómo va tu dinero y qué tienes que hacer (docs/panel-v2.md, 4.1).

Una cifra grande con su fecha (`portfolio.valoracion` sobre la cartera del modo activo), tu plan
por partes, cuántas cosas tocan hoy (`plan.servicio`, lo mismo que `GET /api/plan/hoy`), los avisos
que haya y el mercado en una línea con nombres llanos. Solo se lee; nada se envía.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

from fastapi import APIRouter

from invest_ll.api.modo import (
    almacen_del_broker,
    almacen_del_modo,
    cartera_del_modo,
    modo_efectivo,
    moneda_de_la_cartera,
    nota_de_moneda,
)
from invest_ll.api.schemas_v2 import Inicio, MiniMercado, ParteResumen, Patrimonio
from invest_ll.errors import InvestLLError
from invest_ll.estrategias import datos
from invest_ll.estrategias.catalogo import ficha
from invest_ll.nombres import nombre_llano
from invest_ll.plan import almacen, servicio
from invest_ll.plan.hoy import AVISO_USDT, MONEDA_BOLSA, MONEDA_CRIPTO
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


def _partes(
    plan: almacen.Plan, cartera: Portfolio | None, del_broker: Portfolio | None, libre: Decimal
) -> list[ParteResumen]:
    """Cada parte, valorada donde vive: cripto en la cartera del modo; bolsa en la del bróker (la
    real, en cualquier modo), con lo que tiene sin invertir por las ventas del plan (`libre`)."""
    partes: list[ParteResumen] = []
    for parte in plan.partes:
        f = ficha(parte.estrategia)
        if f is None:  # pragma: no cover - validado al guardar
            continue
        de_bolsa = f.mercado == "bolsa"
        donde = del_broker if de_bolsa else cartera
        efectivo = libre if de_bolsa else Decimal(0)
        valor: Decimal | None = None
        puesto = Decimal(0)
        if donde is not None:
            v = valorar(donde, _precio, solo=f.posee, con_efectivo=False, efectivo_minimo=efectivo)
            valor, puesto = v.valor, v.puesto
        partes.append(
            ParteResumen(
                estrategia=f.clave,
                nombre=f.nombre,
                mercado=f.mercado,
                valor=valor,
                puesto=puesto,
                # La de sus acciones de hoy: lo del bróker se paga en euros; lo de Binance, en USDT.
                moneda=MONEDA_CRIPTO if f.mercado == "cripto" else MONEDA_BOLSA,
                efectivo=efectivo if donde is not None else Decimal(0),
            )
        )
    return partes


@router.get("/inicio", tags=["inicio"])
def inicio() -> Inicio:
    """Tu dinero hoy (cartera del modo activo), el plan resumido, acciones pendientes y avisos."""
    efectivo = modo_efectivo()
    avisos: list[str] = [] if efectivo.aviso is None else [efectivo.aviso]
    actividades: list[Activity] = []
    del_broker: list[Activity] = []
    cartera: Portfolio | None = None
    cartera_del_broker: Portfolio | None = None
    try:
        actividades = almacen_del_modo(efectivo.modo).activities()
        # Lo del bróker se anota siempre en la cartera real (ver `almacen_del_broker`).
        del_broker = almacen_del_broker().activities()
        cartera = derive_portfolio(actividades)
        cartera_del_broker = derive_portfolio(del_broker)
    except InvestLLError as error:
        avisos.append(f"Tu registro de movimientos tiene un problema: {error}")

    try:
        plan = almacen.PlanStore().leer()
    except almacen.PlanIlegibleError as error:
        # Inicio es lo primero que se ve: un plan estropeado se dice aquí, no tumba la pantalla.
        plan = None
        avisos.append(str(error))
    # Lo cobrado al vender en tu bróker con el plan y aún no reinvertido: dinero tuyo, que se
    # cuenta aunque falten ingresos por anotar (sin ellos, el efectivo derivado sale negativo y
    # la venta haría bajar "Tu dinero hoy" en lo que cobraste).
    libre = (
        servicio.lo_del_broker(plan, del_broker).libre
        if cartera_del_broker is not None
        else Decimal(0)
    )

    del_modo = cartera_del_modo(efectivo.modo)
    if cartera is not None:
        v = valorar(cartera, _precio, efectivo_minimo=libre if del_modo == "real" else Decimal(0))
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
            cartera=del_modo,
            # Lo mismo que suma `valorar`: el efectivo derivado si es positivo, y nunca menos de
            # lo que tienes sin invertir en tu bróker por las ventas del plan.
            efectivo=max(cartera.cash, Decimal(0), libre if del_modo == "real" else Decimal(0)),
            moneda=moneda_de_la_cartera(del_modo),
            nota_moneda=nota_de_moneda(
                del_modo,
                [
                    *(p.symbol for p in cartera.open_positions),
                    *(t.symbol for t in cartera.closed_trades),
                ],
            ),
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
            cartera=del_modo,
            efectivo=Decimal(0),
            moneda=moneda_de_la_cartera(del_modo),
            nota_moneda=None,
        )

    pausa = TriggerStore().halted()
    if pausa is not None:
        avisos.append(f"Las compras están en pausa: {pausa}.")

    pendientes = 0
    proxima: date | None = None
    partes: list[ParteResumen] | None = None
    if plan is not None:
        partes = _partes(plan, cartera, cartera_del_broker, libre)
        if cartera is not None:
            resultado = servicio.calcular_hoy(
                plan,
                actividades,
                hoy=servicio.hoy_local(),
                pausa=pausa,
                actividades_bolsa=del_broker,
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
