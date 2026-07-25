"""T010 — almacenamiento del histórico (FR-005)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.loader import load_series
from invest_ll.data.series import PriceSeries
from invest_ll.fetch.provenance import Provenance
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.store import HistoryStore

from ..fixtures.recorded_data import ORIGEN, velas

PROVEEDOR = "recorded"


def peticion(symbol: str = "BTC/USDT") -> FetchRequest:
    return FetchRequest(
        symbol=symbol,
        interval=Interval.DAY_1,
        start=ORIGEN,
        end=ORIGEN + Interval.DAY_1.duration * 10,
        market=Market.CRYPTO,
    )


def serie(n: int = 5) -> PriceSeries:
    return PriceSeries(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        calendar=Continuous24x7(),
        bars=tuple(velas(n)),
    )


def procedencia(n: int = 5) -> Provenance:
    return Provenance(
        provider=PROVEEDOR,
        symbol="BTC/USDT",
        interval="DAY_1",
        market="crypto",
        downloaded_at=datetime(2026, 7, 25, tzinfo=UTC),
        range_start=ORIGEN,
        range_end=ORIGEN + Interval.DAY_1.duration * n,
        bar_count=n,
        prices_adjusted=True,
    )


def test_load_devuelve_none_cuando_no_hay_nada(tmp_path: Path) -> None:
    """Que no exista todavía es el caso normal la primera vez, no un error."""
    assert HistoryStore(tmp_path).load(peticion(), PROVEEDOR) is None


def test_guardar_y_recuperar(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    store.save(peticion(), serie(), procedencia())

    recuperado = store.load(peticion(), PROVEEDOR)
    assert recuperado is not None
    series, prov = recuperado
    assert len(series) == 5
    assert prov.provider == PROVEEDOR


def test_el_csv_lo_carga_el_motor_sin_conversion(tmp_path: Path) -> None:
    """FR-005: el objetivo entero de la feature en un test."""
    store = HistoryStore(tmp_path)
    ruta = store.save(peticion(), serie(), procedencia())

    cargada, avisos = load_series(
        ruta, symbol="BTC/USDT", interval=Interval.DAY_1, calendar=Continuous24x7()
    )
    assert len(cargada) == 5
    assert avisos == ()


def test_el_simbolo_con_barra_no_rompe_la_ruta(tmp_path: Path) -> None:
    """'BTC/USDT' no vale como nombre de carpeta en ningún sistema de ficheros."""
    store = HistoryStore(tmp_path)
    ruta = store.save(peticion("BTC/USDT"), serie(), procedencia())
    assert ruta.exists()
    assert "BTC-USDT" in str(ruta)


def test_la_procedencia_se_guarda_al_lado_y_no_dentro(tmp_path: Path) -> None:
    """Meterla en el CSV rompería la compatibilidad con el loader del motor."""
    store = HistoryStore(tmp_path)
    ruta = store.save(peticion(), serie(), procedencia())
    meta = store.meta_path(peticion(), PROVEEDOR)

    assert meta.exists()
    cabecera = ruta.read_text(encoding="utf-8").splitlines()[0]
    assert cabecera == "timestamp,open,high,low,close,volume"


def test_la_procedencia_sobrevive_al_viaje_de_ida_y_vuelta(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    original = procedencia()
    store.save(peticion(), serie(), original)

    recuperado = store.load(peticion(), PROVEEDOR)
    assert recuperado is not None
    assert recuperado[1].downloaded_at == original.downloaded_at
    assert recuperado[1].bar_count == original.bar_count
