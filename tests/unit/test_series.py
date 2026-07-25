"""T009 — PriceSeries: validación de la serie (FR-015, FR-034)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.series import PriceSeries
from invest_ll.errors import InvalidSeriesError

from ..fixtures.builders import ORIGIN, bar_at, ramp, series_from_closes


def build(bars: tuple[Bar, ...], interval: Interval = Interval.DAY_1) -> PriceSeries:
    return PriceSeries(symbol="TEST", interval=interval, calendar=Continuous24x7(), bars=bars)


def test_serie_valida_se_construye() -> None:
    serie = series_from_closes(ramp(5))
    assert len(serie) == 5
    assert serie.symbol == "TEST"


def test_serie_vacia_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError, match="vacía"):
        build(())


def test_marcas_desordenadas_se_rechazan() -> None:
    day = timedelta(days=1)
    bars = (bar_at(ORIGIN + day, 101.0), bar_at(ORIGIN, 100.0))
    with pytest.raises(InvalidSeriesError, match="cronológico"):
        build(bars)


def test_marcas_duplicadas_se_rechazan() -> None:
    bars = (bar_at(ORIGIN, 100.0), bar_at(ORIGIN, 101.0))
    with pytest.raises(InvalidSeriesError, match="cronológico"):
        build(bars)


def test_marca_desalineada_del_intervalo_se_rechaza() -> None:
    """FR-034: una serie diaria con una vela a media tarde está corrupta."""
    bars = (
        bar_at(ORIGIN, 100.0),
        bar_at(ORIGIN + timedelta(days=1, hours=7), 101.0),
    )
    with pytest.raises(InvalidSeriesError, match=r"alineada|intervalo"):
        build(bars)


def test_intervalo_horario_se_acepta() -> None:
    serie = series_from_closes(ramp(5), interval=Interval.HOUR_1)
    assert serie.interval is Interval.HOUR_1


def test_arrays_numpy_coinciden_con_las_velas() -> None:
    serie = series_from_closes([100.0, 101.0, 102.0])
    assert list(serie.closes) == [100.0, 101.0, 102.0]
    assert len(serie.timestamps) == 3


def test_serie_es_inmutable() -> None:
    serie = series_from_closes(ramp(3))
    with pytest.raises((AttributeError, TypeError)):
        serie.symbol = "OTRO"  # type: ignore[misc]


def test_zonas_horarias_mixtas_se_rechazan() -> None:
    """Comparar marcas de zonas distintas es la vía silenciosa a un orden equivocado."""
    naive_utc = datetime(2026, 1, 2, tzinfo=UTC)
    bars = (bar_at(ORIGIN, 100.0), bar_at(naive_utc.astimezone(UTC), 101.0))
    serie = build(bars)
    assert len(serie) == 2
