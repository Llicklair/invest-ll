"""T008 — validación de Bar (FR-015).

Una vela incoherente es la puerta de entrada a un backtest que miente. Se rechaza en el borde.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from invest_ll.data.bar import Bar
from invest_ll.errors import InvalidSeriesError

TS = datetime(2026, 1, 1, tzinfo=UTC)


def make_bar(**overrides: object) -> Bar:
    fields: dict[str, object] = {
        "timestamp": TS,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "volume": 1000.0,
    }
    fields.update(overrides)
    return Bar(**fields)  # type: ignore[arg-type]


def test_bar_valida_se_construye() -> None:
    bar = make_bar()
    assert bar.close == 105.0


def test_bar_es_inmutable() -> None:
    bar = make_bar()
    with pytest.raises((AttributeError, TypeError)):
        bar.close = 1.0  # type: ignore[misc]


@pytest.mark.parametrize("field", ["open", "high", "low", "close"])
def test_precio_cero_o_negativo_se_rechaza(field: str) -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(**{field: 0.0})
    with pytest.raises(InvalidSeriesError):
        make_bar(**{field: -1.0})


def test_high_menor_que_low_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(high=80.0, low=90.0)


def test_open_fuera_del_rango_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(open=200.0)


def test_close_fuera_del_rango_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(close=10.0)


def test_volumen_negativo_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(volume=-1.0)


def test_volumen_cero_es_valido() -> None:
    """Un periodo sin negociación es legítimo, no un error de datos."""
    assert make_bar(volume=0.0).volume == 0.0


def test_nan_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(close=float("nan"))


def test_infinito_se_rechaza() -> None:
    with pytest.raises(InvalidSeriesError):
        make_bar(high=float("inf"))


def test_timestamp_sin_zona_horaria_se_rechaza() -> None:
    """Una marca sin zona es ambigua: en bolsa determina si el mercado estaba abierto."""
    with pytest.raises(InvalidSeriesError):
        make_bar(timestamp=datetime(2026, 1, 1))
