"""Lógica del panel.

La interfaz de Streamlit no se prueba aquí — se prueba lo que la alimenta, que es donde está el
riesgo. Un panel que muestra cifras de dinero sin tests detrás es justo lo que este proyecto
lleva toda la sesión evitando.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from invest_ll.dashboard.data import (
    discover_assets,
    equity_table,
    metrics_table,
    parse_amount,
    trades_table,
)
from invest_ll.data.bar import Interval
from invest_ll.engine.backtest import run_backtest
from invest_ll.engine.config import FrictionConfig, RiskConfig
from invest_ll.fetch.provenance import Provenance
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.store import HistoryStore
from invest_ll.strategy.moving_average import MovingAverageCrossover

from ..fixtures.builders import series_from_closes, v_shape

D = Decimal
CON_FRICCION = FrictionConfig(commission_rate=D("0.001"), slippage_rate=D("0.0005"))


def informe():  # type: ignore[no-untyped-def]
    return run_backtest(
        series_from_closes(v_shape(200)),
        MovingAverageCrossover(short=5, long=20),
        initial_capital=D(10000),
        friction=CON_FRICCION,
        risk=RiskConfig(position_fraction=D(1)),
    )


class TestDescubrirActivos:
    def test_sin_datos_devuelve_lista_vacia(self, tmp_path: Path) -> None:
        """Es el estado normal antes de la primera descarga, no un error."""
        assert discover_assets(tmp_path) == []

    def test_encuentra_un_historico_descargado(self, tmp_path: Path) -> None:
        peticion = FetchRequest(
            symbol="BTC/USDT",
            interval=Interval.DAY_1,
            start=datetime(2026, 1, 1, tzinfo=UTC),
            end=datetime(2026, 3, 1, tzinfo=UTC),
            market=Market.CRYPTO,
        )
        serie = series_from_closes(v_shape(60), symbol="BTC/USDT")
        procedencia = Provenance(
            provider="ccxt-binance",
            symbol="BTC/USDT",
            interval="DAY_1",
            market="crypto",
            downloaded_at=datetime(2026, 3, 1, tzinfo=UTC),
            range_start=serie.bars[0].timestamp,
            range_end=serie.bars[-1].timestamp,
            bar_count=len(serie),
            prices_adjusted=True,
        )
        HistoryStore(tmp_path).save(peticion, serie, procedencia)

        encontrados = discover_assets(tmp_path)
        assert len(encontrados) == 1
        assert encontrados[0].symbol == "BTC/USDT"
        assert encontrados[0].interval is Interval.DAY_1
        assert encontrados[0].is_crypto

    def test_ignora_las_discrepancias_guardadas(self, tmp_path: Path) -> None:
        """La carpeta de versiones en conflicto no son historicos utilizables."""
        carpeta = tmp_path / "ccxt-binance" / "BTC-USDT" / "discrepancias"
        carpeta.mkdir(parents=True)
        (carpeta / "DAY_1-20260101T000000.csv").write_text(
            "timestamp,open,high,low,close,volume\n", encoding="utf-8"
        )
        assert discover_assets(tmp_path) == []

    def test_ignora_ficheros_con_nombre_desconocido(self, tmp_path: Path) -> None:
        carpeta = tmp_path / "proveedor" / "ACTIVO"
        carpeta.mkdir(parents=True)
        (carpeta / "loquesea.csv").write_text("x", encoding="utf-8")
        assert discover_assets(tmp_path) == []

    def test_un_activo_de_bolsa_no_se_marca_como_cripto(self, tmp_path: Path) -> None:
        carpeta = tmp_path / "yfinance" / "AAPL"
        carpeta.mkdir(parents=True)
        (carpeta / "DAY_1.csv").write_text(
            "timestamp,open,high,low,close,volume\n", encoding="utf-8"
        )
        encontrados = discover_assets(tmp_path)
        assert len(encontrados) == 1
        assert not encontrados[0].is_crypto


class TestTablas:
    def test_la_curva_tiene_una_fila_por_periodo(self) -> None:
        r = informe()
        assert len(equity_table(r)) == len(r.equity_curve)
        assert len(equity_table(r)) > 0

    def test_las_metricas_incluyen_las_obligatorias(self) -> None:
        nombres = {fila["metrica"] for fila in metrics_table(informe())}
        for esperado in ("Resultado neto", "Drawdown maximo", "Operaciones", "Costes totales"):
            assert any(esperado in str(n) for n in nombres)

    def test_el_win_rate_va_el_ultimo_y_con_su_coletilla(self) -> None:
        """Un panel convence mas que un texto: aqui importa mas, no menos."""
        filas = metrics_table(informe())
        ultima = str(filas[-1]["metrica"])
        assert "win rate" in ultima.lower()
        assert "no es criterio" in ultima.lower()

    def test_el_registro_de_operaciones_permite_auditar(self) -> None:
        r = informe()
        filas = trades_table(r)
        assert len(filas) == r.trade_count
        if filas:
            assert filas[0]["motivo"]


class TestImportes:
    def test_convierte_un_numero_valido(self) -> None:
        assert parse_amount("1500.50", campo="capital") == D("1500.50")

    def test_rechaza_texto_no_numerico(self) -> None:
        with pytest.raises(ValueError, match="no es un numero"):
            parse_amount("mucho", campo="capital")

    @pytest.mark.parametrize("valor", ["0", "-100"])
    def test_rechaza_importes_no_positivos(self, valor: str) -> None:
        with pytest.raises(ValueError, match="positivo"):
            parse_amount(valor, campo="capital")


def test_el_panel_no_importa_red_ni_esta_en_el_motor() -> None:
    """El panel puede usar lo que quiera, pero el motor sigue sin conocerlo.

    Complementa a test_engine_isolation: alli se comprueba que el motor no importa red; aqui,
    que tampoco importa el panel.
    """
    import ast

    raiz = Path(__file__).resolve().parents[2] / "src" / "invest_ll"
    for sub in ("engine", "report", "strategy"):
        for fichero in (raiz / sub).rglob("*.py"):
            arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
            for nodo in ast.walk(arbol):
                nombres: list[str] = []
                if isinstance(nodo, ast.Import):
                    nombres = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                    nombres = [nodo.module]
                for nombre in nombres:
                    assert not nombre.startswith("invest_ll.dashboard"), (
                        f"{fichero.name} importa el panel: la dependencia va al reves"
                    )
                    assert nombre != "streamlit", f"{fichero.name} importa streamlit"
