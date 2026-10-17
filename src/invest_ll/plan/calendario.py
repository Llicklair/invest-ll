"""El calendario de aportaciones de un plan: qué ha vencido y qué viene.

Una aportación vence el día del mes del plan (`dia`, de 1 a 28: existe en todos los meses). Cuenta
también la del mes en que se creó el plan, aunque ese día ya hubiera pasado: al guardar el plan
el día 17 con día de aportación 1, lo primero que toca es el inicial y la aportación de ese mes.
Es lo mismo que hace la simulación (`estrategias.simulacion`): el primer mes entran el inicial y la
mensual juntos.
"""

from __future__ import annotations

from datetime import date


def _mes_siguiente(anio: int, mes: int) -> tuple[int, int]:
    return (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def fechas_vencidas(creado: date, dia: int, hoy: date) -> list[date]:
    """Los días de aportación desde el mes de creación hasta hoy, incluido."""
    fechas: list[date] = []
    anio, mes = creado.year, creado.month
    while (anio, mes) <= (hoy.year, hoy.month):
        fecha = date(anio, mes, dia)
        if fecha <= hoy:
            fechas.append(fecha)
        anio, mes = _mes_siguiente(anio, mes)
    return fechas


def vencidas(creado: date, dia: int, hoy: date) -> int:
    """Cuántas aportaciones mensuales han vencido desde que se creó el plan."""
    return len(fechas_vencidas(creado, dia, hoy))


def periodo_actual(creado: date, dia: int, hoy: date) -> date | None:
    """El día de la última aportación vencida (la que toca ahora); `None` si aún no vence ninguna."""
    fechas = fechas_vencidas(creado, dia, hoy)
    return fechas[-1] if fechas else None


def primera(creado: date, dia: int) -> date:
    """El día de la primera aportación del plan."""
    return date(creado.year, creado.month, dia)


def inicio(creado: date, dia: int) -> date:
    """Desde cuándo cuenta lo anotado con el plan: su creación o, si es antes, el día de su
    primera aportación (creado el 17 con día 1, la compra de esa aportación puede ser del 5)."""
    return min(creado, primera(creado, dia))


def proxima(creado: date, dia: int, hoy: date) -> date:
    """El primer día de aportación posterior a hoy."""
    candidata = primera(creado, dia)
    while candidata <= hoy:
        anio, mes = _mes_siguiente(candidata.year, candidata.month)
        candidata = date(anio, mes, dia)
    return candidata
