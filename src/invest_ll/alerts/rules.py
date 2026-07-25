"""Las reglas. Cada una mide una cosa y devuelve una alerta o nada.

Están escritas como funciones sueltas y no como una jerarquía de clases porque cada una se puede
leer, probar y borrar por separado. Una regla que ya no aporte debería poder desaparecer sin tocar
las demás.

**La regla que justifica el módulo es `peor_de_lo_simulado`.** El resto informan de estados que
podrías ver en cualquier aplicación; esa compara lo que estás viviendo con lo que la simulación
te dijo que ibas a vivir. Es la única que conecta el plan con la realidad, y es exactamente la
conversación que este proyecto existe para tener.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.alerts.models import (
    CAIDA_DESDE_MAXIMO,
    DATOS_OBSOLETOS,
    DESVIACION_DEL_PLAN,
    PEOR_DE_LO_SIMULADO,
    PERDIDA_DESDE_TU_ENTRADA,
    Alert,
    Nivel,
    Position,
    Umbrales,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from invest_ll.data.series import PriceSeries

D = Decimal


def _porcentaje(fraccion: Decimal) -> str:
    return f"{fraccion * 100:.1f}%"


def datos_obsoletos(
    serie: PriceSeries, *, ahora: datetime, umbrales: Umbrales | None = None
) -> Alert | None:
    """La serie lleva demasiado sin actualizarse.

    Va la primera de la lista a propósito. Si los datos son viejos, TODAS las demás alertas hablan
    de un mundo que ya no existe — y una alerta tranquilizadora calculada sobre datos de hace un
    mes es peor que ninguna alerta.
    """
    umbrales = umbrales or Umbrales()
    # No se comprueba que la serie tenga velas: `PriceSeries` rechaza las vacias al construirse.
    dias = (ahora - serie.bars[-1].timestamp).days
    if dias < umbrales.dias_sin_datos:
        return None

    return Alert(
        code=DATOS_OBSOLETOS,
        symbol=serie.symbol,
        level=Nivel.REVISAR,
        measured=D(dias),
        threshold=D(umbrales.dias_sin_datos),
        message=(
            f"los datos llevan {dias} dias sin actualizarse (ultima vela: "
            f"{serie.bars[-1].timestamp.date()}). Lo que veas calculado con esta serie describe "
            "ese dia, no hoy."
        ),
    )


def caida_desde_maximo(serie: PriceSeries, *, umbrales: Umbrales | None = None) -> Alert | None:
    """Cuánto ha caído el activo desde su máximo dentro de la serie."""
    umbrales = umbrales or Umbrales()
    if len(serie) < 2:
        return None

    maximo = max(serie.closes)
    actual = serie.closes[-1]
    if maximo <= 0:
        return None

    caida = D(str((maximo - actual) / maximo))
    if caida < umbrales.caida_desde_maximo:
        return None

    return Alert(
        code=CAIDA_DESDE_MAXIMO,
        symbol=serie.symbol,
        level=Nivel.INFORMA,
        measured=caida,
        threshold=umbrales.caida_desde_maximo,
        message=(
            f"esta un {_porcentaje(caida)} por debajo de su maximo en el periodo cargado. "
            "Es un dato del activo, no de tu posicion."
        ),
    )


def peor_de_lo_simulado(
    serie: PriceSeries, *, drawdown_simulado: Decimal, capital: Decimal
) -> Alert | None:
    """La caída real ha superado la que la simulación dijo que aguantarías.

    **La regla que da sentido al módulo.** Cuando alguien acepta un plan acepta implícitamente su
    peor momento: "la simulación decía que en el peor punto perderías 5.668". Si la realidad ya va
    por 12.000, eso no es ruido de mercado — es que el plan ya no describe lo que está pasando.

    Se compara en dinero y no en porcentaje porque es lo que se firmó: el informe de simulación
    da el drawdown en euros sobre un capital concreto.
    """
    if len(serie) < 2 or capital <= 0:
        return None

    referencia = abs(drawdown_simulado)
    if referencia <= 0:
        return None

    maximo = max(serie.closes)
    actual = serie.closes[-1]
    if maximo <= 0:
        return None

    caida_real = D(str((maximo - actual) / maximo)) * capital
    if caida_real <= referencia:
        return None

    return Alert(
        code=PEOR_DE_LO_SIMULADO,
        symbol=serie.symbol,
        level=Nivel.REVISAR,
        measured=caida_real,
        threshold=referencia,
        message=(
            f"la caida actual ({caida_real:,.0f}) ya supera la peor que dio la simulacion "
            f"({referencia:,.0f}). El plan que aceptaste no incluia esto: conviene mirar si "
            "sigue teniendo sentido, no si conviene salir corriendo."
        ),
    )


def perdida_desde_tu_entrada(
    serie: PriceSeries, posicion: Position, *, umbrales: Umbrales | None = None
) -> Alert | None:
    """Lo que llevas perdido TÚ, que no es lo mismo que lo que ha caído el activo.

    Un activo puede estar un 30% por debajo de su máximo y tú ir ganando, si entraste después.
    Confundir las dos cosas es la forma más fácil de asustar a alguien sin motivo.
    """
    umbrales = umbrales or Umbrales()
    actual = D(str(serie.closes[-1]))
    valor = posicion.value_at(actual)
    coste = posicion.cost
    if coste <= 0:
        return None

    variacion = (valor - coste) / coste
    # Solo por perdidas: una alerta que salta porque vas ganando existe para que abras la app.
    if variacion >= 0 or abs(variacion) < umbrales.perdida_desde_entrada:
        return None

    return Alert(
        code=PERDIDA_DESDE_TU_ENTRADA,
        symbol=serie.symbol,
        level=Nivel.INFORMA,
        measured=variacion,
        threshold=-umbrales.perdida_desde_entrada,
        message=(
            f"llevas un {_porcentaje(abs(variacion))} por debajo de tu entrada "
            f"({coste:,.0f} puestos, {valor:,.0f} ahora)."
        ),
    )


def desviacion_del_plan(
    posiciones: Sequence[Position],
    precios: Mapping[str, Decimal],
    objetivo: Mapping[str, Decimal],
    *,
    umbrales: Umbrales | None = None,
) -> list[Alert]:
    """Los pesos reales se han ido de los que decidiste.

    No dice qué hacer. Que la deriva se corrija vendiendo, comprando o esperando depende de cosas
    que este programa no sabe — y cada corrección cuesta comisiones, que es justo lo que más daño
    hace en los números de este repositorio.
    """
    umbrales = umbrales or Umbrales()
    valores = {p.symbol: p.value_at(precios[p.symbol]) for p in posiciones if p.symbol in precios}
    total = sum(valores.values())
    if total <= 0:
        return []

    alertas: list[Alert] = []
    for simbolo, valor in sorted(valores.items()):
        deseado = objetivo.get(simbolo)
        if deseado is None:
            continue
        real = valor / total
        deriva = real - deseado
        if abs(deriva) < umbrales.desviacion_del_plan:
            continue

        direccion = "por encima" if deriva > 0 else "por debajo"
        alertas.append(
            Alert(
                code=DESVIACION_DEL_PLAN,
                symbol=simbolo,
                level=Nivel.INFORMA,
                measured=real,
                threshold=deseado,
                message=(
                    f"pesa un {_porcentaje(real)} de la cartera, {_porcentaje(abs(deriva))} "
                    f"{direccion} del {_porcentaje(deseado)} que decidiste. Corregirlo cuesta "
                    "comisiones; dejarlo cambia el riesgo que asumes."
                ),
            )
        )
    return alertas
