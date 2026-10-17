"""La vista general del mercado.

Lo que se prueba aquí no es que las gráficas se dibujen, sino que **no mientan**: que un activo
sin histórico suficiente no aparezca como si hubiera rendido un 0%, y que la comparación
normalice para que un precio alto no aplaste visualmente a los demás.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from invest_ll.dashboard.data import (
    AvailableAsset,
    discover_assets,
    fetch_args,
    full_history_args,
    market_overview,
    normalised_series,
)
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
        guardar(tmp_path, "CORTO", subida(31))
        fila = market_overview(discover_assets(tmp_path))[0]

        assert fila["1 mes"] is not None, "un mes de velas diarias basta para un mes"
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


class TestLaTablaDensa:
    """Las columnas nuevas del Panorama al estilo CoinMarketCap — sin sus anzuelos."""

    def test_las_variaciones_cortas_salen(self, tmp_path: Path) -> None:
        guardar(tmp_path, "AAA", subida(30))
        fila = market_overview(discover_assets(tmp_path))[0]

        assert fila["1 dia"] is not None
        assert fila["1 semana"] is not None
        assert fila["1 dia"] > 0  # type: ignore[operator]

    def test_no_existe_columna_de_una_hora(self, tmp_path: Path) -> None:
        """El 1h% es el anzuelo de CMC: ninguna aportacion periodica cambia por la ultima hora."""
        guardar(tmp_path, "AAA", subida(30))
        assert "1 hora" not in market_overview(discover_assets(tmp_path))[0]

    def test_ytd_sin_anho_anterior_no_se_inventa(self, tmp_path: Path) -> None:
        """Con datos solo del anho en curso, YTD es 'no se sabe', no un numero."""
        guardar(tmp_path, "AAA", subida(30))  # 30 velas desde 2020-01-01: sin 2019
        assert market_overview(discover_assets(tmp_path))[0]["YTD"] is None

    def test_ytd_cruza_el_anho_cuando_hay_datos(self, tmp_path: Path) -> None:
        # 400 velas diarias desde 2020-01-01 cruzan a 2021.
        guardar(tmp_path, "AAA", [100.0] * 366 + [110.0] * 34)
        fila = market_overview(discover_assets(tmp_path))[0]
        assert fila["YTD"] is not None
        assert fila["YTD"] == 10.0

    def test_la_sparkline_es_el_final_de_la_serie(self, tmp_path: Path) -> None:
        guardar(tmp_path, "AAA", subida(100))
        fila = market_overview(discover_assets(tmp_path))[0]
        chispas = cast("list[float]", fila["sparkline"])
        assert isinstance(chispas, list)
        # Tres meses (91 dias naturales) de velas diarias: el cierre de hace 91 dias y los 91 de
        # despues. Asi la chispa empieza justo donde se mide la variacion de "3 meses".
        assert len(chispas) == 92
        assert chispas[0] == fila["ultimo"] - 91  # type: ignore[operator]
        assert chispas[-1] == fila["ultimo"], "termina en el ultimo cierre"

    def test_las_ventanas_son_de_calendario_tambien_en_cripto(self, tmp_path: Path) -> None:
        """La cripto cotiza los siete dias: contar 252 velas como "un año" eran ocho meses y medio.

        Caso real del panel: Bitcoin salia con "Un mes -2,6 %" en Mercado y "+7,1 %" en Inicio,
        que si mide 30 dias naturales.
        """
        # 400 velas diarias: 100 hasta el dia 34 y 150 desde el 35. Hace 365 dias, el dia 34.
        guardar(tmp_path, "BTC", [100.0] * 35 + [150.0] * 365)
        fila = market_overview(discover_assets(tmp_path))[0]

        assert fila["1 año"] == 50.0, "un año son 365 dias, no 252 velas"
        assert fila["1 mes"] == 0.0
        assert fila["5 años"] is None

    def test_la_fecha_de_los_datos_viaja_en_la_fila(self, tmp_path: Path) -> None:
        """Sin 'datos hasta', una tabla con historicos parados pareceria de hoy."""
        guardar(tmp_path, "AAA", subida(30))
        fila = market_overview(discover_assets(tmp_path))[0]
        assert str(fila["datos hasta"]) == "2020-01-30"


class TestActualizarHistoricos:
    """El comando de re-descarga se reconstruye de la procedencia, no se adivina."""

    def test_reconstruye_el_comando_desde_la_procedencia(self, tmp_path: Path) -> None:
        guardar(tmp_path, "AAA", subida(30))
        activo = discover_assets(tmp_path)[0]
        argumentos = fetch_args(activo, hasta=datetime(2026, 7, 26, tzinfo=UTC))

        assert argumentos is not None
        assert argumentos[:3] == [sys.executable, "-m", "invest_ll.cli_fetch"]
        assert "AAA" in argumentos
        assert "--market" in argumentos and "crypto" in argumentos
        assert "--start" in argumentos and "2020-01-01" in argumentos
        assert "--end" in argumentos and "2026-07-26" in argumentos

    def test_no_pasa_por_uv_run(self, tmp_path: Path) -> None:
        """El panel corre dentro del entorno virtual: `uv run` intentaria resincronizarlo.

        En Windows eso falla con 'os error 32' mientras el ejecutable del panel esta abierto, y
        la descarga moria antes de empezar.
        """
        guardar(tmp_path, "AAA", subida(30))
        activo = discover_assets(tmp_path)[0]
        hasta = datetime(2026, 7, 26, tzinfo=UTC)
        for argumentos in (
            fetch_args(activo, hasta=hasta),
            full_history_args("GLD", market="equity", hasta=hasta),
        ):
            assert argumentos is not None
            assert "uv" not in argumentos[:2]

    def test_la_descarga_nueva_trae_el_historico_completo(self) -> None:
        argumentos = full_history_args(
            "SOL/USDT", market="crypto", hasta=datetime(2026, 10, 17, tzinfo=UTC)
        )
        assert argumentos[3:] == [
            "SOL/USDT",
            "--market",
            "crypto",
            "--interval",
            "DAY_1",
            "--start",
            "2015-01-01",
            "--end",
            "2026-10-17",
            "--exchange",
            "binance",
        ]
        bolsa = full_history_args("GLD", market="equity", hasta=datetime(2026, 10, 17, tzinfo=UTC))
        assert "--exchange" not in bolsa

    def test_sin_procedencia_no_se_adivina(self, tmp_path: Path) -> None:
        """Descargar con parametros supuestos produciria una serie distinta en silencio."""
        guardar(tmp_path, "AAA", subida(30))
        activo = discover_assets(tmp_path)[0]
        sin_meta = AvailableAsset(
            symbol=activo.symbol,
            provider=activo.provider,
            interval=activo.interval,
            path=activo.path,
            provenance=None,
        )
        assert fetch_args(sin_meta, hasta=datetime(2026, 7, 26, tzinfo=UTC)) is None
