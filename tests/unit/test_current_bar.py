"""T022 — la vela en curso se descarta (FR-007).

Guardar como definitivo un periodo que aún no ha cerrado mete en el histórico un dato que todavía
va a cambiar: un backtest de hoy y otro de mañana sobre "el mismo" fichero darían resultados
distintos sin que nada lo explique.
"""

from __future__ import annotations

from invest_ll.data.bar import Interval
from invest_ll.fetch.merge import drop_unclosed

from ..fixtures.recorded_data import ORIGEN, velas

PASO = Interval.DAY_1.duration


def test_la_ultima_vela_sin_cerrar_se_descarta() -> None:
    """5 velas diarias; estamos a mitad de la quinta."""
    ahora = ORIGEN + PASO * 4 + PASO / 2
    cerradas = drop_unclosed(velas(5), interval_duration=PASO, now=ahora)
    assert len(cerradas) == 4


def test_una_vela_justo_cerrada_se_conserva() -> None:
    """El límite es inclusivo: si el periodo ha terminado, el dato ya es definitivo."""
    ahora = ORIGEN + PASO * 5
    assert len(drop_unclosed(velas(5), interval_duration=PASO, now=ahora)) == 5


def test_todas_cerradas_hace_tiempo_se_conservan() -> None:
    ahora = ORIGEN + PASO * 100
    assert len(drop_unclosed(velas(5), interval_duration=PASO, now=ahora)) == 5


def test_todas_sin_cerrar_devuelve_vacio() -> None:
    ahora = ORIGEN
    assert drop_unclosed(velas(5), interval_duration=PASO, now=ahora) == ()


def test_el_instante_va_inyectado_no_se_lee_del_reloj() -> None:
    """Dos llamadas con instantes distintos dan resultados distintos, sin tocar el sistema."""
    temprano = drop_unclosed(velas(10), interval_duration=PASO, now=ORIGEN + PASO * 3)
    tardio = drop_unclosed(velas(10), interval_duration=PASO, now=ORIGEN + PASO * 8)
    assert len(temprano) == 3
    assert len(tardio) == 8


def test_es_determinista() -> None:
    ahora = ORIGEN + PASO * 4
    primera = drop_unclosed(velas(10), interval_duration=PASO, now=ahora)
    segunda = drop_unclosed(velas(10), interval_duration=PASO, now=ahora)
    assert [b.timestamp for b in primera] == [b.timestamp for b in segunda]


def test_una_granularidad_menor_cierra_antes() -> None:
    horario = Interval.HOUR_1.duration
    bars = velas(5, interval=Interval.HOUR_1)
    ahora = ORIGEN + horario * 5
    assert len(drop_unclosed(bars, interval_duration=horario, now=ahora)) == 5
