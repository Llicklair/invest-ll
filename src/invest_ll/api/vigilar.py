"""Pestaña Vigilar: lo que está pasando con tus activos. Se mira; no persigue.

Esta pestaña **no notifica**: existe, y aparece cuando la abres. La FCA midió sobre más de 9.000
personas que las notificaciones aumentan un 11% las operaciones y un 8% las inversiones
arriesgadas. Tampoco hay alertas de subidas: una que dijera "GLD subió un 20%" no informa de nada
que necesites, existe para que abras la aplicación.

Los triggers, cuando se cruzan, PROPONEN la venta exacta como texto; ejecutarla y confirmarla
sigue siendo cosa tuya. La pausa es el nivel 1 del kill switch: deja de proponer entradas nuevas y
no toca las posiciones abiertas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Query

from invest_ll.alerts.engine import NADA_QUE_CONTAR, evaluate
from invest_ll.alerts.models import Nivel, Umbrales
from invest_ll.api.activos import ILEGIBLE, descargados
from invest_ll.api.errores import del_dominio, no_encontrado
from invest_ll.api.modo import almacen_activo
from invest_ll.api.schemas import (
    Alerta,
    Alertas,
    ComprobacionTriggers,
    Disparo,
    NuevoTrigger,
    Pausa,
    TriggerArmado,
    Triggers,
)
from invest_ll.data.series import PriceSeries
from invest_ll.nombres import nombre_llano
from invest_ll.portfolio.derive import derive_portfolio
from invest_ll.portfolio.triggers import (
    Trigger,
    TriggerRule,
    TriggerStore,
    check_triggers,
)

router = APIRouter()


def _armado(trigger: Trigger) -> TriggerArmado:
    return TriggerArmado(
        trigger_id=trigger.trigger_id,
        symbol=trigger.symbol,
        nombre=nombre_llano(trigger.symbol),
        regla=trigger.rule.value,
        umbral=trigger.threshold,
        armado=trigger.armed_at,
        descripcion=trigger.describe(),
    )


@router.get("/vigilar/alertas", tags=["vigilar"])
def alertas(
    dias: int = Query(default=7, ge=1, le=365),
    caida_pct: int = Query(default=15, ge=1, le=99),
) -> Alertas:
    """Alertas de riesgo sobre los históricos. Nunca de subidas."""
    series: list[PriceSeries] = []
    for activo in descargados():
        try:
            series.append(activo.load_completa())
        except ILEGIBLE:
            continue

    with del_dominio():
        umbrales = Umbrales(dias_sin_datos=dias, caida_desde_maximo=Decimal(caida_pct) / 100)
        encontradas = evaluate(series, ahora=datetime.now(UTC), umbrales=umbrales)

    return Alertas(
        alertas=[
            Alerta(
                symbol=a.symbol,
                nivel="revisar" if a.level is Nivel.REVISAR else "informativo",
                mensaje=a.message,
            )
            for a in encontradas
        ],
        # Ni "todo correcto" ni globos: solo lo que se ha mirado y lo que no.
        nada_que_contar=None if encontradas else NADA_QUE_CONTAR,
    )


@router.get("/triggers", tags=["vigilar"])
def triggers() -> Triggers:
    almacen = TriggerStore()
    return Triggers(
        triggers=[_armado(t) for t in almacen.triggers()],
        reglas=[r.value for r in TriggerRule],
        pausa=almacen.halted(),
    )


@router.post("/triggers", tags=["vigilar"], status_code=201)
def armar(nuevo: NuevoTrigger) -> TriggerArmado:
    almacen = TriggerStore()
    with del_dominio():
        trigger = Trigger(
            trigger_id=almacen.next_id(),
            symbol=nuevo.simbolo.strip().upper(),
            rule=TriggerRule(nuevo.regla),
            threshold=Decimal(nuevo.umbral_pct) / 100,
            armed_at=datetime.now(UTC),
        )
        almacen.arm(trigger)
    return _armado(trigger)


@router.delete("/triggers/{trigger_id}", tags=["vigilar"], status_code=204)
def desarmar(trigger_id: str) -> None:
    """404 si no existe: desarmar lo inexistente no es un éxito."""
    if not TriggerStore().disarm(trigger_id):
        raise no_encontrado(f"no hay ningun trigger armado con id {trigger_id!r}")


@router.get("/triggers/comprobar", tags=["vigilar"])
def comprobar_triggers() -> ComprobacionTriggers:
    """Evalúa los triggers contra la cartera del modo activo; los disparos son texto, nada se envía."""
    with del_dominio():
        cartera = derive_portfolio(almacen_activo().activities())
        comprobacion = check_triggers(TriggerStore().triggers(), cartera.open_positions)

    return ComprobacionTriggers(
        disparados=[
            Disparo(
                trigger_id=f.trigger.trigger_id,
                symbol=f.trigger.symbol,
                nombre=nombre_llano(f.trigger.symbol),
                medido=f.measured,
                umbral=f.trigger.threshold,
                cantidad_propuesta=f.quantity,
                precio=f.last_price,
                precio_fecha=fecha.date(),
                comando=f.command,
            )
            for f, fecha in comprobacion.fired
        ],
        sin_evaluar=list(comprobacion.not_evaluated),
        armados=comprobacion.armed,
    )


@router.post("/pausa", tags=["vigilar"], status_code=204)
def pausar(pausa: Pausa) -> None:
    """Nivel 1 del kill switch. 422 si el motivo está vacío."""
    with del_dominio():
        TriggerStore().halt(reason=pausa.motivo, at=datetime.now(UTC))


@router.delete("/pausa", tags=["vigilar"], status_code=204)
def reanudar() -> None:
    """404 si no había pausa."""
    if not TriggerStore().resume():
        raise no_encontrado("No habia ninguna pausa activa.")
