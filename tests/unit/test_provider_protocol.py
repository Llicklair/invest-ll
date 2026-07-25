"""T009 — contrato del proveedor de datos."""

from __future__ import annotations

import pytest

from invest_ll.data.bar import Interval
from invest_ll.fetch.errors import UnknownSymbolError
from invest_ll.fetch.protocol import MarketDataProvider, ProviderCapabilities
from invest_ll.fetch.providers.recorded import RecordedProvider

from ..fixtures.recorded_data import ORIGEN, velas


def test_el_proveedor_grabado_cumple_el_protocolo() -> None:
    assert isinstance(RecordedProvider(velas(5)), MarketDataProvider)


def test_un_objeto_sin_fetch_no_cumple() -> None:
    class NoEsProveedor:
        pass

    assert not isinstance(NoEsProveedor(), MarketDataProvider)


def test_devuelve_velas_en_orden_y_sin_duplicados() -> None:
    provider = RecordedProvider(velas(10))
    obtenidas = provider.fetch(
        "BTC/USDT", Interval.DAY_1, ORIGEN, ORIGEN + Interval.DAY_1.duration * 10
    )
    marcas = [bar.timestamp for bar in obtenidas]
    assert marcas == sorted(marcas)
    assert len(set(marcas)) == len(marcas)


def test_respeta_el_rango_pedido() -> None:
    provider = RecordedProvider(velas(10))
    paso = Interval.DAY_1.duration
    obtenidas = provider.fetch("BTC/USDT", Interval.DAY_1, ORIGEN + paso * 2, ORIGEN + paso * 5)
    assert len(obtenidas) == 3


def test_activo_desconocido_lanza_en_vez_de_devolver_vacio() -> None:
    """Confundir 'no existe' con 'sin datos' produce un histórico vacío con aspecto de válido."""
    provider = RecordedProvider(velas(5), known_symbols=frozenset({"BTC/USDT"}))
    with pytest.raises(UnknownSymbolError):
        provider.fetch("NO-EXISTE", Interval.DAY_1, ORIGEN, ORIGEN + Interval.DAY_1.duration * 5)


def test_cuenta_las_llamadas() -> None:
    """El contador es lo que hace verificable SC-005."""
    provider = RecordedProvider(velas(5))
    assert provider.calls == 0
    provider.fetch("BTC/USDT", Interval.DAY_1, ORIGEN, ORIGEN + Interval.DAY_1.duration)
    assert provider.calls == 1


class TestCapabilities:
    def test_se_declaran(self) -> None:
        caps = RecordedProvider(velas(1), name="x", adjusts_prices=False).capabilities
        assert caps.name == "x"
        assert not caps.adjusts_prices

    def test_sin_intervalos_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="intervalo"):
            ProviderCapabilities(
                name="vacio",
                supported_intervals=frozenset(),
                adjusts_prices=True,
                includes_delisted=True,
                max_bars_per_request=100,
            )

    def test_limite_no_positivo_se_rechaza(self) -> None:
        with pytest.raises(ValueError, match="positivo"):
            ProviderCapabilities(
                name="malo",
                supported_intervals=frozenset({Interval.DAY_1}),
                adjusts_prices=True,
                includes_delisted=True,
                max_bars_per_request=0,
            )
