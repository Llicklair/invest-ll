"""T008 — validación de la solicitud de histórico."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from invest_ll.data.bar import Interval
from invest_ll.fetch.request import FetchRequest, Market

INICIO = datetime(2026, 1, 1, tzinfo=UTC)
FIN = datetime(2026, 2, 1, tzinfo=UTC)


def build(**overrides: object) -> FetchRequest:
    campos: dict[str, object] = {
        "symbol": "BTC/USDT",
        "interval": Interval.DAY_1,
        "start": INICIO,
        "end": FIN,
        "market": Market.CRYPTO,
    }
    campos.update(overrides)
    return FetchRequest(**campos)  # type: ignore[arg-type]


def test_solicitud_valida() -> None:
    assert build().symbol == "BTC/USDT"


def test_es_inmutable() -> None:
    with pytest.raises((AttributeError, TypeError)):
        build().symbol = "OTRO"  # type: ignore[misc]


def test_rango_invertido_se_rechaza() -> None:
    with pytest.raises(ValueError, match=r"anterior|rango"):
        build(start=FIN, end=INICIO)


def test_rango_vacio_se_rechaza() -> None:
    with pytest.raises(ValueError, match=r"anterior|rango"):
        build(start=INICIO, end=INICIO)


@pytest.mark.parametrize("campo", ["start", "end"])
def test_marca_sin_zona_se_rechaza(campo: str) -> None:
    """Sin zona no se sabe qué periodo se está pidiendo."""
    with pytest.raises(ValueError, match="zona"):
        build(**{campo: datetime(2026, 1, 15)})


def test_simbolo_vacio_se_rechaza() -> None:
    with pytest.raises(ValueError, match=r"activo|símbolo|simbolo"):
        build(symbol="  ")


def test_el_mercado_determina_el_calendario() -> None:
    assert build(market=Market.CRYPTO).is_continuous
    assert not build(symbol="AAPL", market=Market.EQUITY).is_continuous


def test_nombre_seguro_para_ruta() -> None:
    """'BTC/USDT' no puede ser un nombre de carpeta."""
    assert "/" not in build().path_key
    assert build().path_key
