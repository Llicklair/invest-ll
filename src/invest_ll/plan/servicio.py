"""Junta lo que "Qué toca hoy" necesita del disco y se lo pasa al cálculo puro (`hoy`).

Lee el plan, la cartera del modo, los paneles de datos y el reparto que cada estrategia quiere
hoy; `plan.hoy.calcular` hace las cuentas. Si falta algo, no se inventa: se devuelve el aviso de
qué falta y cómo traerlo.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from invest_ll import llano
from invest_ll.errors import InvestLLError
from invest_ll.estrategias import datos, objetivo
from invest_ll.estrategias.catalogo import ficha
from invest_ll.nombres import base, es_cripto
from invest_ll.plan import calendario
from invest_ll.plan.hoy import (
    EnElBroker,
    Entrada,
    ParteDeHoy,
    Precio,
    Resultado,
    calcular,
    en_el_broker,
)
from invest_ll.portfolio.derive import derive_portfolio

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence

    from invest_ll.estrategias.catalogo import Mercado
    from invest_ll.plan.almacen import Plan
    from invest_ll.portfolio.models import Activity

DIAS_DATOS_VIEJOS: Final = 3
"""Más días que estos desde el último cierre, y se avisa antes de operar con esos precios."""


def hoy_local() -> date:
    """El día de hoy en la hora de quien usa el panel: el día del mes del plan es de calendario."""
    return datetime.now().astimezone().date()


def fecha_de_creacion(plan: Plan) -> date:
    return plan.creado.astimezone().date()


def _parte(
    plan: Plan, mercado: Mercado, hoy: date, avisos: list[str], tenidos: Sequence[str]
) -> ParteDeHoy | None:
    guardada = plan.parte_de(mercado, ficha)
    if guardada is None:
        return None
    encontrada = ficha(guardada.estrategia)
    if encontrada is None:  # pragma: no cover - validado al guardar
        return None
    quiere = objetivo.de_hoy(encontrada)
    p = datos.panel(mercado)
    if quiere is None or p is None:
        avisos.append(f"{encontrada.nombre}: {datos.motivo_sin_datos(mercado)}")
        return None
    if (hoy - quiere.fecha).days > DIAS_DATOS_VIEJOS:
        avisos.append(
            f"Los precios de {encontrada.nombre} son del {llano.fecha_corta(quiere.fecha)}: "
            f"actualízalos antes de operar con: {datos.COMANDOS[mercado]}"
        )
    precios: dict[str, Precio] = {}
    for activo in {*quiere.pesos, *tenidos}:
        consulta = f"{activo}USDT" if mercado == "cripto" else activo
        visto = datos.cierre_en_panel(p, consulta)
        if visto is not None:
            precios[activo] = Precio(valor=visto.precio, fecha=visto.fecha)
    return ParteDeHoy(
        ficha=encontrada,
        inicial=guardada.inicial,
        mensual=guardada.mensual,
        objetivo=dict(quiere.pesos),
        precios=precios,
    )


def calcular_hoy(
    plan: Plan,
    actividades: Sequence[Activity],
    *,
    hoy: date,
    pausa: str | None,
    actividades_bolsa: Sequence[Activity] | None = None,
) -> Resultado:
    """Qué toca hoy con este plan y estos movimientos (los de la cartera del modo activo).

    `actividades_bolsa` son los de la cartera real, donde se anota lo del bróker en cualquier
    modo; sin ellos, se usan los mismos `actividades`.
    """
    avisos: list[str] = []
    posiciones: dict[str, Decimal] = {}
    cartera_legible = True
    try:
        derivada = derive_portfolio(actividades)
        posiciones = {p.symbol: p.quantity for p in derivada.open_positions}
    except InvestLLError as error:
        cartera_legible = False
        avisos.append(
            f"Tu registro de movimientos cuenta una historia imposible ({error}): no se calcula "
            "lo de Binance hasta arreglarlo."
        )
    tenidos_cripto = [base(s) for s in posiciones if es_cripto(s)]
    cripto = _parte(plan, "cripto", hoy, avisos, tenidos_cripto) if cartera_legible else None
    # Lo del bróker se mira en su cartera (la real): para saber si sobra algo que vender hace
    # falta lo que tienes y el precio de cada fondo tenido, también de los que la estrategia ya no
    # quiere (no están en su objetivo de hoy).
    posiciones_bolsa = posiciones
    broker_legible = cartera_legible
    if actividades_bolsa is not None:
        try:
            del_broker = derive_portfolio(actividades_bolsa)
            posiciones_bolsa = {p.symbol: p.quantity for p in del_broker.open_positions}
            broker_legible = True
        except InvestLLError as error:
            posiciones_bolsa = {}
            broker_legible = False
            avisos.append(
                f"Tu registro de movimientos cuenta una historia imposible ({error}): no se mira "
                "si toca vender algo en tu bróker hasta arreglarlo."
            )
    tenidos_bolsa = [base(s) for s in posiciones_bolsa if not es_cripto(s)]
    bolsa = _parte(plan, "bolsa", hoy, avisos, tenidos_bolsa)
    resultado = calcular(
        Entrada(
            hoy=hoy,
            creado=fecha_de_creacion(plan),
            dia=plan.dia_del_mes,
            actividades=actividades,
            posiciones=posiciones,
            cripto=cripto,
            bolsa=bolsa,
            pausa=pausa,
            actividades_bolsa=actividades_bolsa,
            posiciones_bolsa=posiciones_bolsa,
            broker_legible=broker_legible,
        )
    )
    return Resultado(
        acciones=resultado.acciones,
        avisos=tuple(dict.fromkeys([*avisos, *resultado.avisos])),
        proxima_fecha=resultado.proxima_fecha,
        resumen=resultado.resumen,
    )


def lo_del_broker(
    plan: Plan | None, actividades: Sequence[Activity], *, hasta: date | None = None
) -> EnElBroker:
    """Lo que el plan tiene en tu bróker: unidades por fondo y lo que está sin invertir.

    `actividades` son las de la cartera real (donde se anota lo del bróker). Vacío sin plan, o si
    el registro cuenta una historia imposible (eso ya lo avisa quien deriva la cartera).
    """
    if plan is None:
        return EnElBroker(unidades={}, libre=Decimal(0))
    try:
        derivada = derive_portfolio(actividades)
    except InvestLLError:
        return EnElBroker(unidades={}, libre=Decimal(0))
    posiciones = {p.symbol: p.quantity for p in derivada.open_positions}
    return en_el_broker(
        actividades,
        calendario.inicio(fecha_de_creacion(plan), plan.dia_del_mes),
        posiciones,
        hasta=hasta,
    )


def precio_de_referencia(simbolo: str, fecha: date, respaldo: Decimal | None) -> Decimal | None:
    """El cierre del fondo de referencia el día de la compra (o el último antes)."""
    visto = datos.cierre_hasta(simbolo, fecha)
    if visto is not None and fecha - visto.fecha <= timedelta(days=7):
        return visto.precio
    return respaldo
