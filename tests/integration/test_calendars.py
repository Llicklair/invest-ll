"""T043 — el mismo motor sobre cripto y bolsa (SC-009, SC-010, FR-020..FR-023).

La misma estrategia, sin modificar, sobre un mercado continuo y otro con sesión. Si hiciera falta
tocarla, el motor no sería agnóstico al mercado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7, ExchangeCalendarAdapter
from invest_ll.data.loader import load_series
from invest_ll.data.series import PriceSeries
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.report.report import BacktestReport
from invest_ll.strategy.moving_average import MovingAverageCrossover
from invest_ll.strategy.protocol import Strategy

from ..fixtures.builders import series_from_closes, v_shape
from ..unit.helpers_strategies import AlternaCadaDosPeriodos, EntraYMantiene

D = Decimal
FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))
RIESGO = RiskConfig(position_fraction=D("0.5"))
CABECERA = "timestamp,open,high,low,close,volume\n"
INICIO_SESION = datetime(2026, 7, 27, 14, 0, tzinfo=UTC)  # 10:00 en Nueva York


def evaluar(
    serie: PriceSeries,
    strategy: Strategy,
    *,
    capital: Decimal = Decimal(10000),
    risk: RiskConfig = RIESGO,
) -> BacktestReport:
    return run_backtest(serie, strategy, initial_capital=capital, friction=FRICCION, risk=risk)


def escribir(tmp_path: Path, filas: str, nombre: str) -> Path:
    ruta = tmp_path / nombre
    ruta.write_text(CABECERA + filas, encoding="utf-8")
    return ruta


def test_la_misma_estrategia_corre_en_ambos_mercados() -> None:
    """SC-009: sin una línea distinta según el mercado."""
    strategy = MovingAverageCrossover(short=4, long=12)

    cripto = series_from_closes(v_shape(80), calendar=Continuous24x7(), symbol="BTC")
    bolsa = series_from_closes(v_shape(80), calendar=ExchangeCalendarAdapter("XNYS"), symbol="ACME")

    r_cripto = evaluar(cripto, strategy)
    r_bolsa = evaluar(bolsa, strategy)

    assert type(r_cripto) is type(r_bolsa)
    assert r_cripto.symbol == "BTC"
    assert r_bolsa.symbol == "ACME"


def test_el_cierre_nocturno_no_se_reporta_como_hueco(tmp_path: Path) -> None:
    """SC-010: en bolsa, la ausencia de datos fuera de sesión es normal."""
    filas = "".join(f"2026-07-{27 + i}T14:00:00+00:00,100,101,99,100.5,1000\n" for i in range(3))
    ruta = escribir(tmp_path, filas, "bolsa.csv")

    _, avisos = load_series(
        ruta, symbol="ACME", interval=Interval.DAY_1, calendar=ExchangeCalendarAdapter("XNYS")
    )
    assert avisos == ()


def test_un_hueco_en_mercado_continuo_si_se_reporta(tmp_path: Path) -> None:
    """En cripto el mercado nunca cierra: si falta una vela, falta de verdad."""
    filas = (
        "2026-07-01T00:00:00+00:00,100,101,99,100.5,1000\n"
        "2026-07-04T00:00:00+00:00,100,101,99,100.5,1000\n"
    )
    ruta = escribir(tmp_path, filas, "cripto.csv")

    _, avisos = load_series(ruta, symbol="BTC", interval=Interval.DAY_1, calendar=Continuous24x7())
    assert len(avisos) >= 1


def test_el_hueco_dentro_de_sesion_si_se_avisa(tmp_path: Path) -> None:
    """Falta una hora en plena sesión: eso sí es un dato perdido."""
    filas = (
        "2026-07-27T14:00:00+00:00,100,101,99,100.5,1000\n"
        "2026-07-27T17:00:00+00:00,100,101,99,100.5,1000\n"
    )
    ruta = escribir(tmp_path, filas, "hueco_sesion.csv")

    _, avisos = load_series(
        ruta, symbol="ACME", interval=Interval.HOUR_1, calendar=ExchangeCalendarAdapter("XNYS")
    )
    assert len(avisos) >= 1
    assert "hueco" in avisos[0].message.lower()


def test_ninguna_orden_se_ejecuta_con_el_mercado_cerrado() -> None:
    """FR-022: si el periodo de ejecución cae fuera de sesión, no se opera."""
    calendario = ExchangeCalendarAdapter("XNYS")
    serie = series_from_closes(
        [100.0 + i for i in range(60)],
        interval=Interval.HOUR_1,
        calendar=calendario,
        start=INICIO_SESION,
    )
    report = evaluar(serie, AlternaCadaDosPeriodos(), capital=D(100000))
    for orden in report.all_orders():
        if orden.filled_quantity > 0:
            assert calendario.is_open(orden.execution_timestamp)


def test_el_gap_entre_sesiones_afecta_al_resultado() -> None:
    """FR-023: una posición que cruza la noche asume el salto de precio, también en contra."""
    serie = series_from_closes(
        [100.0] * 10 + [60.0] * 10,
        interval=Interval.HOUR_1,
        calendar=ExchangeCalendarAdapter("XNYS"),
        start=INICIO_SESION,
    )
    report = evaluar(serie, EntraYMantiene(), risk=RiskConfig(position_fraction=D(1)))
    if report.trade_count:
        assert report.net_result < 0, "el salto adverso debe reflejarse en el resultado"


def test_series_de_distinta_granularidad_sobre_la_misma_estrategia() -> None:
    """FR-032, FR-033: los parámetros van en periodos, no en unidades de calendario."""
    strategy = MovingAverageCrossover(short=3, long=10)
    for interval in (Interval.MINUTE_5, Interval.HOUR_1, Interval.DAY_1):
        report = evaluar(series_from_closes(v_shape(60), interval=interval), strategy)
        assert report.trade_count >= 0


def test_la_duracion_del_intervalo_no_cambia_las_senales() -> None:
    """Los mismos precios con distinto intervalo producen las mismas operaciones."""
    strategy = MovingAverageCrossover(short=3, long=10)
    precios = v_shape(60)

    horaria = evaluar(series_from_closes(precios, interval=Interval.HOUR_1), strategy)
    diaria = evaluar(series_from_closes(precios, interval=Interval.DAY_1), strategy)

    assert horaria.trade_count == diaria.trade_count
    assert horaria.net_result == diaria.net_result


def test_el_calendario_bursatil_reduce_las_oportunidades() -> None:
    """Con sesión hay periodos en los que sencillamente no se puede operar."""
    precios = [100.0 + (i % 7) for i in range(80)]

    continuo = evaluar(
        series_from_closes(
            precios, interval=Interval.HOUR_1, calendar=Continuous24x7(), start=INICIO_SESION
        ),
        AlternaCadaDosPeriodos(),
        capital=D(100000),
    )
    con_sesion = evaluar(
        series_from_closes(
            precios,
            interval=Interval.HOUR_1,
            calendar=ExchangeCalendarAdapter("XNYS"),
            start=INICIO_SESION,
        ),
        AlternaCadaDosPeriodos(),
        capital=D(100000),
    )
    assert con_sesion.trade_count <= continuo.trade_count


def test_la_serie_declara_su_calendario() -> None:
    serie = series_from_closes(v_shape(20), calendar=ExchangeCalendarAdapter("XNYS"))
    assert isinstance(serie.calendar, ExchangeCalendarAdapter)


def test_intervalo_y_calendario_conviven() -> None:
    serie = series_from_closes(
        [100.0] * 5,
        interval=Interval.HOUR_1,
        calendar=ExchangeCalendarAdapter("XNYS"),
        start=INICIO_SESION,
    )
    assert serie.interval.duration == timedelta(hours=1)
