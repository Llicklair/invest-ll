"""Backtest sobre velas DIARIAS de bolsa.

Regresión de un fallo que estuvo vivo dos commits y que solo apareció al medir datos reales:
tras normalizar las marcas diarias a medianoche UTC, ninguna caía dentro del horario de sesión
del NYSE. El motor exige mercado abierto para ejecutar, así que **ninguna orden se ejecutaba** y
el backtest devolvía cero operaciones sin error ninguno.

Los tests de calendario que existían usaban series *horarias* fechadas en mitad de la sesión, así
que no cubrían el caso más común de todos: una serie diaria de bolsa.

La lección de diseño: preguntar "¿está abierto el mercado en este instante?" no tiene sentido
para una vela que representa un día entero. La pregunta correcta es "¿este día fue sesión?".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import ExchangeCalendarAdapter
from invest_ll.data.series import PriceSeries
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.strategy.moving_average import MovingAverageCrossover

D = Decimal
UN_DIA = timedelta(days=1)


def serie_bursatil_diaria(closes: list[float]) -> PriceSeries:
    """Velas diarias fechadas a medianoche UTC, como las deja el proveedor de bolsa."""
    inicio = datetime(2025, 1, 2, tzinfo=UTC)
    bars = tuple(
        Bar(
            timestamp=inicio + UN_DIA * i,
            open=precio,
            high=precio + 1,
            low=precio - 1,
            close=precio,
            volume=1000.0,
        )
        for i, precio in enumerate(closes)
    )
    return PriceSeries(
        symbol="AAPL",
        interval=Interval.DAY_1,
        calendar=ExchangeCalendarAdapter("XNYS"),
        bars=bars,
    )


def v_shape(n: int) -> list[float]:
    mitad = n // 2
    baja = [200.0 - i for i in range(mitad)]
    sube = [baja[-1] + (i + 1) for i in range(n - mitad)]
    return baja + sube


def test_una_vela_diaria_a_medianoche_cuenta_como_sesion() -> None:
    """El corazón del fallo: medianoche UTC no es horario de sesión, pero el día sí lo es."""
    calendario = ExchangeCalendarAdapter("XNYS")
    jueves = datetime(2025, 1, 2, tzinfo=UTC)  # dia habil

    assert not calendario.is_open(jueves), "a medianoche UTC el NYSE esta cerrado"
    assert calendario.is_session(jueves), "pero ese dia si fue sesion"


def test_un_fin_de_semana_no_es_sesion() -> None:
    calendario = ExchangeCalendarAdapter("XNYS")
    domingo = datetime(2025, 1, 5, tzinfo=UTC)
    assert not calendario.is_session(domingo)


def test_un_backtest_diario_de_bolsa_produce_operaciones() -> None:
    """Lo que fallaba en real: cero operaciones sobre un año entero de Apple."""
    serie = serie_bursatil_diaria(v_shape(120))
    informe = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005")),
        risk=RiskConfig(position_fraction=D(1)),
    )
    assert informe.trade_count >= 1, "ninguna orden se ejecuto sobre una serie diaria de bolsa"


def test_las_ordenes_se_ejecutan_en_dias_de_sesion() -> None:
    calendario = ExchangeCalendarAdapter("XNYS")
    serie = serie_bursatil_diaria(v_shape(120))
    informe = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D(0)),
        risk=RiskConfig(position_fraction=D(1)),
    )
    for orden in informe.all_orders():
        if orden.filled_quantity > 0:
            assert calendario.is_session(orden.execution_timestamp)


def test_una_serie_diaria_de_cripto_sigue_funcionando() -> None:
    """El arreglo no puede romper el mercado continuo."""
    from invest_ll.data.calendars import Continuous24x7

    inicio = datetime(2025, 1, 1, tzinfo=UTC)
    bars = tuple(
        Bar(
            timestamp=inicio + UN_DIA * i,
            open=precio,
            high=precio + 1,
            low=precio - 1,
            close=precio,
            volume=1000.0,
        )
        for i, precio in enumerate(v_shape(120))
    )
    serie = PriceSeries(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        calendar=Continuous24x7(),
        bars=bars,
    )
    informe = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=D(10000),
        friction=FrictionConfig(commission_rate=D("0.001"), slippage_rate=D(0)),
        risk=RiskConfig(position_fraction=D(1)),
    )
    assert informe.trade_count >= 1
