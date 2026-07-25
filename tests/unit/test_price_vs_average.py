"""Estrategia precio contra media."""

from __future__ import annotations

import pytest

from invest_ll.data.series import PriceSeries
from invest_ll.engine.view import MarketView
from invest_ll.strategy.price_vs_average import PriceVsAverage
from invest_ll.strategy.protocol import SignalKind, Strategy

from ..fixtures.builders import ramp, series_from_closes


def vista(closes: list[float], cursor: int | None = None) -> MarketView:
    serie: PriceSeries = series_from_closes(closes)
    return MarketView(serie, cursor=len(closes) - 1 if cursor is None else cursor)


def test_cumple_el_protocolo() -> None:
    assert isinstance(PriceVsAverage(), Strategy)


def test_sin_historico_suficiente_no_decide() -> None:
    assert PriceVsAverage(periods=30).decide(vista(ramp(10))) is None


def test_entra_cuando_el_precio_supera_la_media() -> None:
    # Diez planos y luego una subida: el ultimo cierre queda muy por encima de la media.
    closes = [100.0] * 10 + [120.0]
    señal = PriceVsAverage(periods=5).decide(vista(closes))
    assert señal is not None
    assert señal.kind is SignalKind.ENTER_LONG


def test_sale_cuando_el_precio_cae_bajo_la_media() -> None:
    closes = [100.0] * 10 + [80.0]
    señal = PriceVsAverage(periods=5).decide(vista(closes))
    assert señal is not None
    assert señal.kind is SignalKind.EXIT


def test_sin_margen_sale_al_primer_cierre_por_debajo() -> None:
    """El 'primer indicio' literal: basta con cerrar un centimo bajo la media."""
    closes = [100.0] * 10 + [99.9]
    señal = PriceVsAverage(periods=5, exit_margin=0.0).decide(vista(closes))
    assert señal is not None
    assert señal.kind is SignalKind.EXIT


def test_con_margen_una_caida_pequena_no_saca() -> None:
    """El margen existe para no salir por una oscilacion normal."""
    closes = [100.0] * 10 + [99.9]
    assert PriceVsAverage(periods=5, exit_margin=0.02).decide(vista(closes)) is None


def test_con_margen_una_caida_grande_si_saca() -> None:
    closes = [100.0] * 10 + [90.0]
    señal = PriceVsAverage(periods=5, exit_margin=0.02).decide(vista(closes))
    assert señal is not None
    assert señal.kind is SignalKind.EXIT


def test_la_media_solo_usa_el_pasado_visible() -> None:
    """Principio II: el futuro de la serie no puede influir en la decision de hoy.

    Misma serie, mismo cursor, pero una tiene datos posteriores muy distintos. La decision debe
    ser identica.
    """
    corta = [100.0] * 10 + [120.0]
    larga = [*corta, 5.0, 5.0, 5.0, 5.0]

    a = PriceVsAverage(periods=5).decide(vista(corta, cursor=10))
    b = PriceVsAverage(periods=5).decide(vista(larga, cursor=10))

    assert a is not None
    assert b is not None
    assert a.kind is b.kind


def test_es_determinista() -> None:
    closes = [100.0] * 10 + [120.0]
    estrategia = PriceVsAverage(periods=5)
    assert estrategia.decide(vista(closes)) == estrategia.decide(vista(closes))


@pytest.mark.parametrize("periodos", [0, 1, -5])
def test_periodos_invalidos_se_rechazan(periodos: int) -> None:
    with pytest.raises(ValueError, match="periodos"):
        PriceVsAverage(periods=periodos)


def test_margen_negativo_se_rechaza() -> None:
    with pytest.raises(ValueError, match="negativo"):
        PriceVsAverage(exit_margin=-0.1)
