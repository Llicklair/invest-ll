"""Junta las reglas y devuelve lo que hay que contar.

Lo único que hace de más respecto a llamar a las reglas una a una es **ordenar**: los datos
obsoletos van primero porque invalidan todo lo demás, y lo que pide revisión va antes que lo que
solo informa. Un listado en orden arbitrario acaba leyéndose por encima, y una alerta que no se
lee no protege de nada.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from invest_ll.alerts.models import DATOS_OBSOLETOS, Alert, Nivel, Umbrales
from invest_ll.alerts.rules import (
    caida_desde_maximo,
    datos_obsoletos,
    desviacion_del_plan,
    peor_de_lo_simulado,
    perdida_desde_tu_entrada,
)

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from invest_ll.alerts.models import Position
    from invest_ll.data.series import PriceSeries

D = Decimal

# Sin alertas el mensaje NO es "todo va bien": es que ninguna regla ha saltado. No es lo mismo, y
# decir lo primero seria tranquilizar sobre cosas que este programa no mide.
NADA_QUE_CONTAR = (
    "Ninguna regla ha saltado.\n"
    "  Eso no significa que todo vaya bien: significa que nada ha cruzado un umbral de los que\n"
    "  se miran aqui. No se vigila la solvencia de las empresas, ni las noticias, ni tu\n"
    "  situacion personal."
)


def _orden(alerta: Alert) -> tuple[int, int, str]:
    """Obsoletos primero, luego lo que pide revision, y dentro de cada grupo por simbolo."""
    return (
        0 if alerta.code == DATOS_OBSOLETOS else 1,
        0 if alerta.level is Nivel.REVISAR else 1,
        alerta.symbol or "",
    )


def evaluate(
    series: Sequence[PriceSeries],
    *,
    ahora: datetime,
    posiciones: Sequence[Position] = (),
    objetivo: Mapping[str, Decimal] | None = None,
    drawdown_simulado: Decimal | None = None,
    capital: Decimal | None = None,
    umbrales: Umbrales | None = None,
) -> list[Alert]:
    """Todas las alertas que aplican, ordenadas por lo que conviene mirar antes.

    Todo lo opcional lo es de verdad: sin posiciones se evalúan las reglas del activo, sin
    `drawdown_simulado` no se compara contra el plan. Pedir la configuración completa para
    obtener algo útil habría convertido esto en una función que nadie llama.
    """
    umbrales = umbrales or Umbrales()
    por_simbolo = {p.symbol: p for p in posiciones}
    alertas: list[Alert] = []

    for serie in series:
        if (obsoleto := datos_obsoletos(serie, ahora=ahora, umbrales=umbrales)) is not None:
            alertas.append(obsoleto)

        if (caida := caida_desde_maximo(serie, umbrales=umbrales)) is not None:
            alertas.append(caida)

        if drawdown_simulado is not None and capital is not None:
            peor = peor_de_lo_simulado(serie, drawdown_simulado=drawdown_simulado, capital=capital)
            if peor is not None:
                alertas.append(peor)

        posicion = por_simbolo.get(serie.symbol)
        if posicion is not None:
            perdida = perdida_desde_tu_entrada(serie, posicion, umbrales=umbrales)
            if perdida is not None:
                alertas.append(perdida)

    if objetivo and posiciones:
        precios = {s.symbol: D(str(s.closes[-1])) for s in series if s.closes[-1] > 0}
        alertas.extend(desviacion_del_plan(posiciones, precios, objetivo, umbrales=umbrales))

    return sorted(alertas, key=_orden)


def render(alertas: Sequence[Alert]) -> str:
    """El listado para leer. Sin alertas dice qué NO se ha comprobado, no que todo vaya bien."""
    if not alertas:
        return NADA_QUE_CONTAR

    revisar = [a for a in alertas if a.level is Nivel.REVISAR]
    cabecera = f"{len(alertas)} alerta(s)"
    if revisar:
        cabecera += f", {len(revisar)} para revisar"

    return "\n".join([cabecera, "-" * 70, *(a.render() for a in alertas)])
