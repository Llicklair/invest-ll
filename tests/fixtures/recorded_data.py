"""Respuestas grabadas de proveedor para los tests (T020).

Deterministas y pequeñas: cuando un test falla, el fallo es del código, no de unos datos que
nadie entiende.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from invest_ll.data.bar import Bar, Interval

ORIGEN = datetime(2026, 1, 1, tzinfo=UTC)


def velas(
    n: int,
    *,
    start: datetime = ORIGEN,
    interval: Interval = Interval.DAY_1,
    base: float = 100.0,
    step: float = 1.0,
) -> list[Bar]:
    """Serie ascendente, con apertura y cierre iguales para no introducir ambigüedad."""
    paso: timedelta = interval.duration
    salida: list[Bar] = []
    for i in range(n):
        precio = base + step * i
        salida.append(
            Bar(
                timestamp=start + paso * i,
                open=precio,
                high=precio + 0.5,
                low=precio - 0.5,
                close=precio,
                volume=1000.0 + i,
            )
        )
    return salida


def velas_con_hueco(n: int, *, salto_en: int, interval: Interval = Interval.DAY_1) -> list[Bar]:
    """Serie a la que le falta una vela intermedia, para probar la detección de huecos."""
    todas = velas(n, interval=interval)
    return [bar for i, bar in enumerate(todas) if i != salto_en]


def alterar(bars: list[Bar], indice: int, *, nuevo_cierre: float) -> list[Bar]:
    """Devuelve la misma serie con una vela cambiada: simula una revisión del proveedor."""
    copia = list(bars)
    original = copia[indice]
    copia[indice] = Bar(
        timestamp=original.timestamp,
        open=original.open,
        high=max(original.high, nuevo_cierre),
        low=min(original.low, nuevo_cierre),
        close=nuevo_cierre,
        volume=original.volume,
    )
    return copia
