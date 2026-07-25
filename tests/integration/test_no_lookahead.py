"""T035 — la estrategia tramposa (SC-003, Principio II).

El test más importante del proyecto. Aquí el éxito de la estrategia es el fracaso del motor: si
una estrategia consigue leer el futuro y el backtest termina con un resultado bonito, todo lo
demás que este proyecto calcula es ficción.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.engine.view import MarketView
from invest_ll.errors import LookAheadError
from invest_ll.strategy.protocol import Signal, SignalKind

from ..fixtures.builders import ramp, series_from_closes

D = Decimal
SIN_FRICCION = FrictionConfig(commission_rate=D(0), slippage_rate=D(0))
TODO = RiskConfig(position_fraction=D(1))


class OraculoPerfecto:
    """Intenta ver la vela siguiente para comprar solo cuando va a subir.

    Si el motor se lo permitiera, obtendría un resultado espectacular e imposible.
    """

    def decide(self, view: MarketView) -> Signal | None:
        futura = view.bar_at(-1)
        if futura.close > view.current_bar.close:
            return Signal(kind=SignalKind.ENTER_LONG)
        return Signal(kind=SignalKind.EXIT)


class TrampaPorIndiceLejano:
    """Variante que salta varios periodos hacia adelante."""

    def decide(self, view: MarketView) -> Signal | None:
        view.bar_at(-10)
        return None


def test_la_estrategia_tramposa_no_obtiene_resultado() -> None:
    """El backtest NO debe completar. Si completa, el motor está roto."""
    serie = series_from_closes(ramp(50))
    with pytest.raises(LookAheadError):
        run_backtest(
            serie,
            OraculoPerfecto(),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )


def test_la_trampa_lejana_tambien_falla() -> None:
    serie = series_from_closes(ramp(50))
    with pytest.raises(LookAheadError):
        run_backtest(
            serie,
            TrampaPorIndiceLejano(),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )


def test_el_motor_no_captura_el_lookahead_para_continuar() -> None:
    """Un backtest contaminado no produce un resultado degradado: no produce resultado.

    Devolver un informe "parcial" sería lo peor de ambos mundos: una cifra que parece válida y
    no lo es.
    """
    serie = series_from_closes(ramp(50))
    try:
        run_backtest(
            serie,
            OraculoPerfecto(),
            initial_capital=D(10000),
            friction=SIN_FRICCION,
            risk=TODO,
        )
    except LookAheadError as error:
        assert "futuro" in str(error).lower()
    else:  # pragma: no cover
        pytest.fail("el motor devolvió un informe pese al acceso a datos futuros")


def test_la_vista_no_ofrece_ninguna_via_publica_al_futuro() -> None:
    """Recorre la superficie pública de MarketView buscando una fuga."""
    serie = series_from_closes(ramp(20))
    view = MarketView(serie, cursor=5)
    visibles = {bar.timestamp for bar in view.history(len(view))}
    futuras = {bar.timestamp for bar in serie.bars[6:]}
    assert not (visibles & futuras)

    for nombre in (n for n in dir(view) if not n.startswith("_")):
        atributo = getattr(view, nombre)
        if callable(atributo):
            continue
        assert not isinstance(atributo, type(serie)), f"'{nombre}' expone la serie completa"
