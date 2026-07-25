"""La vista general del mercado.

Lo que se prueba aquí no es que las gráficas se dibujen, sino que **no mientan**: que un activo
sin histórico suficiente no aparezca como si hubiera rendido un 0%, y que la comparación
normalice para que un precio alto no aplaste visualmente a los demás.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invest_ll.dashboard.data import discover_assets, market_overview, normalised_series
from invest_ll.data.bar import Bar, Interval
from invest_ll.data.calendars import Continuous24x7
from invest_ll.data.series import PriceSeries
from invest_ll.fetch.provenance import Provenance
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.store import HistoryStore

INICIO = datetime(2020, 1, 1, tzinfo=UTC)


def guardar(tmp_path: Path, symbol: str, cierres: list[float]) -> None:
    bars = tuple(
        Bar(
            timestamp=INICIO + Interval.DAY_1.duration * i,
            open=c,
            high=c * 1.01,
            low=c * 0.99,
            close=c,
            volume=1000.0,
        )
        for i, c in enumerate(cierres)
    )
    serie = PriceSeries(
        symbol=symbol, interval=Interval.DAY_1, calendar=Continuous24x7(), bars=bars
    )
    peticion = FetchRequest(
        symbol=symbol,
        interval=Interval.DAY_1,
        start=INICIO,
        end=bars[-1].timestamp,
        market=Market.CRYPTO,
    )
    procedencia = Provenance(
        provider="test",
        symbol=symbol,
        interval="DAY_1",
        market="crypto",
        downloaded_at=datetime(2026, 1, 1, tzinfo=UTC),
        range_start=bars[0].timestamp,
        range_end=bars[-1].timestamp,
        bar_count=len(bars),
        prices_adjusted=True,
    )
    HistoryStore(tmp_path).save(peticion, serie, procedencia)


def subida(n: int, desde: float = 100.0) -> list[float]:
    return [desde + i for i in range(n)]


class TestTablaDeRendimiento:
    def test_una_fila_por_activo(self, tmp_path: Path) -> None:
        guardar(tmp_path, "AAA", subida(300))
        guardar(tmp_path, "BBB", subida(300, 50.0))
        assert len(market_overview(discover_assets(tmp_path))) == 2

    def test_sin_historico_suficiente_no_dice_cero(self, tmp_path: Path) -> None:
        """Un activo sin datos para una ventana NO ha rendido un 0%: no se sabe.

        Confundir ambas cosas mete un activo que no existia en una comparacion.
        """
        guardar(tmp_path, "CORTO", subida(30))
        fila = market_overview(discover_assets(tmp_path))[0]

        assert fila["1 mes"] is not None, "30 velas bastan para un mes"
        assert fila["1 año"] is None, "30 velas NO bastan para un anho"
        assert fila["5 años"] is None

    def test_la_distancia_al_maximo_es_negativa_tras_caer(self, tmp_path: Path) -> None:
        """La columna que menos se mira y mas importa."""
        cierres = subida(100) + [200.0 - i for i in range(50)]
        guardar(tmp_path, "CAIDO", cierres)
        fila = market_overview(discover_assets(tmp_path))[0]

        assert fila["desde maximo"] is not None
        assert fila["desde maximo"] < 0  # type: ignore[operator]

    def test_en_maximo_historico_la_distancia_es_cero(self, tmp_path: Path) -> None:
        guardar(tmp_path, "ARRIBA", subida(200))
        assert market_overview(discover_assets(tmp_path))[0]["desde maximo"] == 0.0

    def test_incluye_que_es_cada_activo(self, tmp_path: Path) -> None:
        """Una tabla de siglas no le sirve a quien no sabe de inversion."""
        guardar(tmp_path, "GLD", subida(300))
        assert market_overview(discover_assets(tmp_path))[0]["que es"] == "Oro"

    def test_un_activo_desconocido_no_se_inventa_descripcion(self, tmp_path: Path) -> None:
        guardar(tmp_path, "ZZZZ", subida(300))
        assert market_overview(discover_assets(tmp_path))[0]["que es"] == "—"

    def test_sin_activos_no_rompe(self) -> None:
        assert market_overview([]) == []


class TestComparacionNormalizada:
    def test_todos_empiezan_en_cien(self, tmp_path: Path) -> None:
        """Sin normalizar, Bitcoin a 90.000 aplasta al oro aunque el oro lo haya batido."""
        guardar(tmp_path, "CARO", [50000.0 + i * 100 for i in range(100)])
        guardar(tmp_path, "BARATO", [10.0 + i * 0.1 for i in range(100)])

        puntos = normalised_series(discover_assets(tmp_path))
        primeros = {p["activo"] for p in puntos if p["valor"] == 100.0}
        assert len(primeros) == 2

    def test_la_normalizacion_conserva_quien_gana(self, tmp_path: Path) -> None:
        """Lo que importa no es el precio, es la variacion. El barato aqui sube mas."""
        guardar(tmp_path, "CARO", [1000.0 + i for i in range(100)])  # +9,9%
        guardar(tmp_path, "BARATO", [10.0 + i for i in range(100)])  # +990%

        puntos = normalised_series(discover_assets(tmp_path))
        finales = {p["activo"]: p["valor"] for p in puntos}
        assert finales["BARATO"] > finales["CARO"]  # type: ignore[operator]

    def test_el_tramo_recorta_por_el_final(self, tmp_path: Path) -> None:
        guardar(tmp_path, "AAA", subida(300))
        completo = normalised_series(discover_assets(tmp_path))
        tramo = normalised_series(discover_assets(tmp_path), periods=50)

        assert len(tramo) == 50
        assert len(completo) == 300
        assert tramo[-1]["fecha"] == completo[-1]["fecha"], "el tramo acaba en el ultimo dato"

    def test_el_tramo_rebasea_a_cien(self, tmp_path: Path) -> None:
        """Al recortar, el 100 debe ser el inicio del TRAMO, no el del historico."""
        guardar(tmp_path, "AAA", subida(300))
        tramo = normalised_series(discover_assets(tmp_path), periods=50)
        assert tramo[0]["valor"] == 100.0

    def test_sin_activos_no_rompe(self) -> None:
        assert normalised_series([]) == []
