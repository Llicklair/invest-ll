"""T048, T049, T050 — procedencia y honestidad sobre el dato (US4).

Los avisos se **derivan** de lo que el proveedor declara, no de que alguien se acuerde de
ponerlos. Un aviso que depende de la memoria de quien escribe el código acaba faltando justo
cuando importa.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.fetch.protocol import ProviderCapabilities
from invest_ll.fetch.provenance import (
    Provenance,
    WarningKind,
    warnings_from_capabilities,
)
from invest_ll.fetch.providers.recorded import RecordedProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import fetch_history
from invest_ll.fetch.store import HistoryStore

from ..fixtures.recorded_data import ORIGEN, velas

PASO = Interval.DAY_1.duration
AHORA = ORIGEN + PASO * 500


def sin_espera(_segundos: float) -> None:
    pass


def capacidades(*, adjusts: bool = True, delisted: bool = True) -> ProviderCapabilities:
    return ProviderCapabilities(
        name="proveedor-test",
        supported_intervals=frozenset({Interval.DAY_1}),
        adjusts_prices=adjusts,
        includes_delisted=delisted,
        max_bars_per_request=1000,
    )


def peticion(market: Market = Market.CRYPTO) -> FetchRequest:
    return FetchRequest(
        symbol="BTC/USDT" if market is Market.CRYPTO else "AAPL",
        interval=Interval.DAY_1,
        start=ORIGEN,
        end=ORIGEN + PASO * 20,
        market=market,
    )


class TestAvisosDerivados:
    def test_sin_ajuste_de_precios_se_avisa(self) -> None:
        """FR-030: cada split aparecería como un desplome que nunca ocurrió."""
        avisos = warnings_from_capabilities(capacidades(adjusts=False), is_equity=True)
        assert any(a.kind is WarningKind.UNADJUSTED_PRICES for a in avisos)

    def test_sin_activos_retirados_se_avisa_del_sesgo(self) -> None:
        """FR-018: el backtest sale mejor de lo que la realidad fue."""
        avisos = warnings_from_capabilities(capacidades(delisted=False), is_equity=True)
        assert any(a.kind is WarningKind.SURVIVORSHIP_BIAS for a in avisos)

    def test_un_proveedor_completo_no_genera_avisos(self) -> None:
        assert warnings_from_capabilities(capacidades(), is_equity=True) == ()

    def test_en_cripto_no_aplican_esos_avisos(self) -> None:
        """No hay splits ni dividendos, y el concepto de 'retirada de bolsa' no encaja."""
        avisos = warnings_from_capabilities(
            capacidades(adjusts=False, delisted=False), is_equity=False
        )
        assert avisos == ()

    def test_el_aviso_de_sesgo_dice_que_no_se_corrige(self) -> None:
        """Prometer lo contrario sería la falsa garantía que la constitución prohíbe."""
        avisos = warnings_from_capabilities(capacidades(delisted=False), is_equity=True)
        mensaje = next(a for a in avisos if a.kind is WarningKind.SURVIVORSHIP_BIAS).message
        assert "no se corrige" in mensaje.lower()

    def test_el_aviso_de_ajuste_explica_la_consecuencia(self) -> None:
        avisos = warnings_from_capabilities(capacidades(adjusts=False), is_equity=True)
        mensaje = next(a for a in avisos if a.kind is WarningKind.UNADJUSTED_PRICES).message
        assert "split" in mensaje.lower()


class TestProcedencia:
    def test_registra_quien_cuando_y_que(self, tmp_path: Path) -> None:
        """SC-007."""
        momento = datetime(2026, 7, 25, 10, 30, tzinfo=UTC)
        resultado = fetch_history(
            peticion(),
            RecordedProvider(velas(20), name="proveedor-test"),
            HistoryStore(tmp_path),
            now=momento,
            sleep=sin_espera,
        )
        p = resultado.provenance
        assert p.provider == "proveedor-test"
        assert p.symbol == "BTC/USDT"
        assert p.interval == "DAY_1"
        assert p.downloaded_at == momento
        assert p.bar_count == 20

    def test_registra_si_los_precios_estan_ajustados(self, tmp_path: Path) -> None:
        resultado = fetch_history(
            peticion(Market.EQUITY),
            RecordedProvider(velas(20), adjusts_prices=True),
            HistoryStore(tmp_path),
            now=AHORA,
            sleep=sin_espera,
        )
        assert resultado.provenance.prices_adjusted

    def test_sobrevive_a_json_y_vuelta(self) -> None:
        original = Provenance(
            provider="p",
            symbol="BTC/USDT",
            interval="DAY_1",
            market="crypto",
            downloaded_at=datetime(2026, 7, 25, tzinfo=UTC),
            range_start=ORIGEN,
            range_end=ORIGEN + PASO * 10,
            bar_count=10,
            prices_adjusted=True,
            quality_warnings=warnings_from_capabilities(
                capacidades(delisted=False), is_equity=True
            ),
        )
        recuperado = Provenance.from_json(original.to_json())
        assert recuperado == original

    def test_se_puede_describir_en_consola(self) -> None:
        """En Windows la consola usa cp1252: un acento de más y no se ve nada."""
        p = Provenance(
            provider="p",
            symbol="AAPL",
            interval="DAY_1",
            market="equity",
            downloaded_at=datetime(2026, 7, 25, tzinfo=UTC),
            range_start=ORIGEN,
            range_end=ORIGEN + PASO * 10,
            bar_count=10,
            prices_adjusted=False,
        )
        p.describe().encode("cp1252")


class TestCredenciales:
    """FR-023, SC-008: ninguna credencial en la procedencia ni en los errores."""

    SOSPECHOSAS = ("api_key", "apikey", "secret", "token", "password", "passphrase")

    def test_la_procedencia_no_tiene_campos_de_credencial(self) -> None:
        campos = set(Provenance.__dataclass_fields__)
        for sospechosa in self.SOSPECHOSAS:
            assert not any(sospechosa in campo.lower() for campo in campos)

    def test_las_capacidades_tampoco(self) -> None:
        campos = set(ProviderCapabilities.__dataclass_fields__)
        for sospechosa in self.SOSPECHOSAS:
            assert not any(sospechosa in campo.lower() for campo in campos)

    def test_el_json_de_procedencia_no_contiene_credenciales(self, tmp_path: Path) -> None:
        resultado = fetch_history(
            peticion(),
            RecordedProvider(velas(20)),
            HistoryStore(tmp_path),
            now=AHORA,
            sleep=sin_espera,
        )
        texto = resultado.provenance.to_json().lower()
        for sospechosa in self.SOSPECHOSAS:
            assert sospechosa not in texto

    def test_los_proveedores_no_piden_credenciales(self) -> None:
        """FR-022: al menos un proveedor por mercado funciona sin claves.

        Ambos las evitan, así que no hay ningún secreto que se pueda filtrar.
        """
        import inspect

        from invest_ll.fetch.providers.crypto import CcxtProvider
        from invest_ll.fetch.providers.equity import YFinanceProvider

        for clase in (CcxtProvider, YFinanceProvider):
            parametros = set(inspect.signature(clase.__init__).parameters)
            for sospechosa in self.SOSPECHOSAS:
                assert not any(sospechosa in p.lower() for p in parametros)
