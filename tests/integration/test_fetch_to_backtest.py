"""T025 — de la descarga al backtest sin conversión manual (US1, SC-001).

La razón de ser de toda la feature 002 en un test: que el motor deje de medir series inventadas.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.fetch.providers.recorded import RecordedProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import fetch_history
from invest_ll.fetch.store import HistoryStore
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.recorded_data import ORIGEN, velas

PASO = Interval.DAY_1.duration
AHORA = ORIGEN + PASO * 500


def peticion(n: int = 120) -> FetchRequest:
    return FetchRequest(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        start=ORIGEN,
        end=ORIGEN + PASO * n,
        market=Market.CRYPTO,
    )


def sin_espera(_segundos: float) -> None:
    """La suite no espera de verdad."""


def descargar(tmp_path: Path, n: int = 120):  # type: ignore[no-untyped-def]
    provider = RecordedProvider(velas(n))
    return (
        fetch_history(
            peticion(n),
            provider,
            HistoryStore(tmp_path),
            now=AHORA,
            sleep=sin_espera,
        ),
        provider,
    )


def test_lo_descargado_se_backtestea_sin_tocar_nada(tmp_path: Path) -> None:
    """SC-001: ni editar, ni convertir, ni renombrar."""
    resultado, _ = descargar(tmp_path)

    serie, avisos = load_series(
        resultado.path,
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        calendar=Continuous24x7(),
    )
    informe = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=Decimal(10000),
        friction=FrictionConfig(commission_rate=Decimal("0.001"), slippage_rate=Decimal("0.0005")),
        risk=RiskConfig(position_fraction=Decimal("0.5")),
        data_warnings=avisos,
    )

    assert informe.symbol == "BTC/USDT"
    assert informe.render()


def test_el_informe_identifica_el_activo_real(tmp_path: Path) -> None:
    resultado, _ = descargar(tmp_path)
    assert resultado.provenance.symbol == "BTC/USDT"
    assert resultado.provenance.bar_count == 120


def test_los_avisos_de_calidad_llegan_al_informe(tmp_path: Path) -> None:
    """Un aviso que se queda en un fichero de metadatos no lo lee nadie."""
    from invest_ll.fetch.provenance import as_data_warnings

    resultado, _ = descargar(tmp_path)
    serie, _ = load_series(
        resultado.path, symbol="BTC/USDT", interval=Interval.DAY_1, calendar=Continuous24x7()
    )
    informe = run_backtest(
        serie,
        MovingAverageCrossover(short=5, long=20),
        initial_capital=Decimal(10000),
        friction=FrictionConfig(commission_rate=Decimal("0.001"), slippage_rate=Decimal(0)),
        risk=RiskConfig(position_fraction=Decimal("0.5")),
        data_warnings=as_data_warnings(resultado.warnings),
    )
    assert len(informe.data_warnings) == len(resultado.warnings)


def test_la_segunda_descarga_no_pide_nada(tmp_path: Path) -> None:
    """SC-005: si ya está todo, cero peticiones al proveedor."""
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(120))

    fetch_history(peticion(), provider, store, now=AHORA, sleep=sin_espera)
    llamadas_tras_la_primera = provider.calls

    fetch_history(peticion(), provider, store, now=AHORA, sleep=sin_espera)
    assert provider.calls == llamadas_tras_la_primera


def test_ampliar_solo_pide_lo_que_falta(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(200))

    fetch_history(peticion(100), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(200), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.added_count == 100
    assert segunda.requests_made == 1


def test_el_historico_crece_sin_perder_lo_anterior(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(200))

    primera = fetch_history(peticion(100), provider, store, now=AHORA, sleep=sin_espera)
    assert primera.series is not None
    primera_vela = primera.series.bars[0]

    segunda = fetch_history(peticion(200), provider, store, now=AHORA, sleep=sin_espera)
    assert segunda.series is not None
    assert segunda.series.bars[0].timestamp == primera_vela.timestamp
    assert len(segunda.series) == 200


def test_la_procedencia_queda_en_disco(tmp_path: Path) -> None:
    _, provider = descargar(tmp_path)
    meta = HistoryStore(tmp_path).meta_path(peticion(), provider.capabilities.name)
    assert meta.exists()
    assert "downloaded_at" in meta.read_text(encoding="utf-8")


def test_una_descarga_de_bolsa_avisa_del_sesgo(tmp_path: Path) -> None:
    """FR-018: el sesgo de supervivencia se advierte, no se corrige."""
    from invest_ll.fetch.provenance import WarningKind

    peticion_bolsa = FetchRequest(
        symbol="AAPL",
        interval=Interval.DAY_1,
        start=datetime(2026, 7, 1, tzinfo=UTC),
        end=datetime(2026, 7, 20, tzinfo=UTC),
        market=Market.EQUITY,
    )
    provider = RecordedProvider(
        velas(12, start=datetime(2026, 7, 1, tzinfo=UTC)),
        name="bolsa-test",
        includes_delisted=False,
    )
    resultado = fetch_history(
        peticion_bolsa,
        provider,
        HistoryStore(tmp_path),
        now=datetime(2026, 8, 1, tzinfo=UTC),
        sleep=sin_espera,
    )
    tipos = {a.kind for a in resultado.warnings}
    assert WarningKind.SURVIVORSHIP_BIAS in tipos
