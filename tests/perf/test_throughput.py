"""T054 — rendimiento (SC-001).

Un backtest que tarda una hora no se usa: el operador deja de probar ideas. El objetivo no es
ser rápido por deporte, es que probar sea barato.
"""

from __future__ import annotations

import time
from decimal import Decimal

import pytest

from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes

pytestmark = pytest.mark.perf

D = Decimal
PERIODOS = 100_000
LIMITE_SEGUNDOS = 60.0


def serie_larga() -> list[float]:
    """Onda determinista de ~100.000 periodos, con cruces de medias frecuentes."""
    import math

    return [100.0 + 20.0 * math.sin(i / 50.0) + (i % 7) for i in range(PERIODOS)]


def test_cien_mil_periodos_en_menos_de_un_minuto() -> None:
    serie = series_from_closes(serie_larga())

    inicio = time.perf_counter()
    report = run_backtest(
        serie,
        MovingAverageCrossover(short=10, long=30),
        initial_capital=D(100000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005")),
        risk=RiskConfig(position_fraction=D("0.5")),
    )
    transcurrido = time.perf_counter() - inicio

    assert transcurrido < LIMITE_SEGUNDOS, (
        f"{PERIODOS} periodos tardaron {transcurrido:.1f}s, por encima del limite de "
        f"{LIMITE_SEGUNDOS}s (SC-001)"
    )
    assert report.trade_count > 0, "sin operaciones no se mide nada util"
