"""T023, T024 — errores y validación de la descarga (FR-009, FR-019, FR-020)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from invest_ll.data.bar import Interval
from invest_ll.fetch.errors import NoDataError, UnknownSymbolError, UnsupportedIntervalError
from invest_ll.fetch.provenance import WarningKind
from invest_ll.fetch.providers.recorded import RecordedProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import fetch_history
from invest_ll.fetch.store import HistoryStore

from ..fixtures.recorded_data import ORIGEN, velas, velas_con_hueco

PASO = Interval.DAY_1.duration
AHORA = ORIGEN + PASO * 500


def sin_espera(_segundos: float) -> None:
    pass


def peticion(symbol: str = "BTC/USDT", n: int = 20) -> FetchRequest:
    return FetchRequest(
        symbol=symbol,
        interval=Interval.DAY_1,
        start=ORIGEN,
        end=ORIGEN + PASO * n,
        market=Market.CRYPTO,
    )


def descargar(tmp_path: Path, provider: RecordedProvider, req: FetchRequest | None = None):  # type: ignore[no-untyped-def]
    return fetch_history(
        req or peticion(), provider, HistoryStore(tmp_path), now=AHORA, sleep=sin_espera
    )


class TestErrores:
    def test_activo_desconocido(self, tmp_path: Path) -> None:
        provider = RecordedProvider(velas(20), known_symbols=frozenset({"BTC/USDT"}))
        with pytest.raises(UnknownSymbolError):
            descargar(tmp_path, provider, peticion("NO-EXISTE"))

    def test_activo_desconocido_no_deja_fichero(self, tmp_path: Path) -> None:
        """FR-009: nada a medias que luego parezca un histórico válido."""
        provider = RecordedProvider(velas(20), known_symbols=frozenset({"BTC/USDT"}))
        with pytest.raises(UnknownSymbolError):
            descargar(tmp_path, provider, peticion("NO-EXISTE"))
        assert list(tmp_path.rglob("*.csv")) == []

    def test_rango_sin_datos(self, tmp_path: Path) -> None:
        with pytest.raises(NoDataError):
            descargar(tmp_path, RecordedProvider([]))

    def test_rango_sin_datos_no_deja_fichero(self, tmp_path: Path) -> None:
        with pytest.raises(NoDataError):
            descargar(tmp_path, RecordedProvider([]))
        assert list(tmp_path.rglob("*.csv")) == []

    def test_granularidad_no_soportada(self, tmp_path: Path) -> None:
        """Se comprueba antes de pedir nada: fallar pronto y con un mensaje útil."""
        provider = RecordedProvider(velas(20), supported_intervals=frozenset({Interval.HOUR_1}))
        with pytest.raises(UnsupportedIntervalError, match="DAY_1"):
            descargar(tmp_path, provider)

    def test_granularidad_no_soportada_no_gasta_peticiones(self, tmp_path: Path) -> None:
        provider = RecordedProvider(velas(20), supported_intervals=frozenset({Interval.HOUR_1}))
        with pytest.raises(UnsupportedIntervalError):
            descargar(tmp_path, provider)
        assert provider.calls == 0

    def test_el_mensaje_dice_que_granularidades_hay(self, tmp_path: Path) -> None:
        provider = RecordedProvider(
            velas(20), supported_intervals=frozenset({Interval.HOUR_1, Interval.MINUTE_5})
        )
        with pytest.raises(UnsupportedIntervalError, match="HOUR_1"):
            descargar(tmp_path, provider)


class TestValidacion:
    def test_los_huecos_se_reportan_y_no_se_rellenan(self, tmp_path: Path) -> None:
        """FR-020: un hueco debe notarse, no taparse con datos inventados."""
        con_hueco = velas_con_hueco(20, salto_en=10)
        resultado = descargar(tmp_path, RecordedProvider(con_hueco))

        assert resultado.provenance.bar_count == 19
        assert any(a.kind is WarningKind.GAP for a in resultado.warnings)

    def test_una_serie_valida_no_genera_avisos_de_hueco(self, tmp_path: Path) -> None:
        resultado = descargar(tmp_path, RecordedProvider(velas(20)))
        assert not any(a.kind is WarningKind.GAP for a in resultado.warnings)

    def test_cobertura_parcial_se_avisa(self, tmp_path: Path) -> None:
        """El operador creería estar evaluando un periodo que no tiene."""
        resultado = descargar(tmp_path, RecordedProvider(velas(5)), peticion(n=100))
        assert any(a.kind is WarningKind.PARTIAL_RANGE for a in resultado.warnings)

    def test_el_aviso_de_cobertura_dice_el_rango_real(self, tmp_path: Path) -> None:
        resultado = descargar(tmp_path, RecordedProvider(velas(5)), peticion(n=100))
        aviso = next(a for a in resultado.warnings if a.kind is WarningKind.PARTIAL_RANGE)
        assert "2026-01" in aviso.message


class TestFalloDelProveedor:
    def test_el_historico_previo_sobrevive_a_un_fallo(self, tmp_path: Path) -> None:
        """FR-015: agotados los reintentos, lo local queda intacto."""
        from invest_ll.fetch.errors import ProviderUnavailableError

        store = HistoryStore(tmp_path)
        bueno = RecordedProvider(velas(20), name="recorded")
        fetch_history(peticion(), bueno, store, now=AHORA, sleep=sin_espera)

        caido = RecordedProvider(velas(40), name="recorded", fail_times=99)
        with pytest.raises(ProviderUnavailableError):
            fetch_history(peticion(n=40), caido, store, now=AHORA, sleep=sin_espera)

        recuperado = store.load(peticion(), "recorded")
        assert recuperado is not None
        assert len(recuperado[0]) == 20


def test_una_fecha_futura_no_trae_velas_sin_cerrar(tmp_path: Path) -> None:
    """Combinación de FR-007 con el rango: nada que aún no haya cerrado entra al fichero."""
    ahora = ORIGEN + PASO * 10
    resultado = fetch_history(
        peticion(n=20),
        RecordedProvider(velas(20)),
        HistoryStore(tmp_path),
        now=ahora,
        sleep=sin_espera,
    )
    assert resultado.provenance.range_end + PASO <= ahora
    assert resultado.provenance.bar_count == 10


def test_el_instante_de_descarga_queda_registrado(tmp_path: Path) -> None:
    momento = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    resultado = fetch_history(
        peticion(),
        RecordedProvider(velas(20)),
        HistoryStore(tmp_path),
        now=momento,
        sleep=sin_espera,
    )
    assert resultado.provenance.downloaded_at == momento


def test_pedir_desde_un_festivo_no_avisa_de_cobertura_parcial(tmp_path: Path) -> None:
    """Regresion encontrada al descargar AAPL de verdad.

    Pedir desde el 1 de enero y recibir desde el 2 no es cobertura parcial: el 1 de enero no hubo
    sesion. El aviso saltaba en cada descarga de bolsa, y un aviso que salta siempre es ruido que
    acaba tapando los avisos que si importan.
    """
    from datetime import UTC, datetime

    from invest_ll.fetch.provenance import WarningKind

    # 2026-01-01 es festivo; el mercado abre el 2.
    peticion_bolsa = FetchRequest(
        symbol="AAPL",
        interval=Interval.DAY_1,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 10, tzinfo=UTC),
        market=Market.EQUITY,
    )
    # Ocho velas desde el 2 cubren hasta el 10: no falta nada al final, solo el festivo inicial.
    velas_desde_el_2 = velas(8, start=datetime(2026, 1, 2, tzinfo=UTC))
    resultado = fetch_history(
        peticion_bolsa,
        RecordedProvider(velas_desde_el_2),
        HistoryStore(tmp_path),
        now=datetime(2026, 3, 1, tzinfo=UTC),
        sleep=sin_espera,
    )
    assert not any(a.kind is WarningKind.PARTIAL_RANGE for a in resultado.warnings)


def test_una_cobertura_realmente_parcial_sigue_avisando(tmp_path: Path) -> None:
    """La tolerancia al festivo no puede silenciar el aviso de verdad."""
    from datetime import UTC, datetime

    from invest_ll.fetch.provenance import WarningKind

    peticion_bolsa = FetchRequest(
        symbol="AAPL",
        interval=Interval.DAY_1,
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 6, 1, tzinfo=UTC),  # cinco meses
        market=Market.EQUITY,
    )
    resultado = fetch_history(
        peticion_bolsa,
        RecordedProvider(velas(6, start=datetime(2026, 1, 2, tzinfo=UTC))),  # solo una semana
        HistoryStore(tmp_path),
        now=datetime(2026, 8, 1, tzinfo=UTC),
        sleep=sin_espera,
    )
    assert any(a.kind is WarningKind.PARTIAL_RANGE for a in resultado.warnings)
