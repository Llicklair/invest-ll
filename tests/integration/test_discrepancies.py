"""T033, T034, T037 — un histórico ya usado no cambia a espaldas del operador (US2).

Sin esto, dos backtests del "mismo" periodo pueden dar resultados distintos sin explicación, y la
reproducibilidad que la feature 001 garantiza se cae por debajo.
"""

from __future__ import annotations

from pathlib import Path

from invest_ll.data.bar import Bar, Interval
from invest_ll.fetch.providers.recorded import RecordedProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import FetchResult, fetch_history, verify_history
from invest_ll.fetch.store import HistoryStore

from ..fixtures.recorded_data import ORIGEN, alterar, velas

PASO = Interval.DAY_1.duration
AHORA = ORIGEN + PASO * 500
PROVEEDOR = "recorded"


def sin_espera(_segundos: float) -> None:
    pass


def peticion(n: int = 20) -> FetchRequest:
    return FetchRequest(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        start=ORIGEN,
        end=ORIGEN + PASO * n,
        market=Market.CRYPTO,
    )


def descargar(store: HistoryStore, bars: list[Bar], n: int = 20) -> FetchResult:
    return fetch_history(peticion(n), RecordedProvider(bars), store, now=AHORA, sleep=sin_espera)


class TestRedescargaIdentica:
    def test_no_genera_discrepancias(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        datos = velas(20)
        descargar(store, datos)
        segunda = descargar(store, datos)
        assert segunda.discrepancies == ()

    def test_no_cambia_el_fichero(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        datos = velas(20)
        primera = descargar(store, datos)
        contenido = primera.path.read_text(encoding="utf-8")

        descargar(store, datos)
        assert primera.path.read_text(encoding="utf-8") == contenido

    def test_no_deja_carpeta_de_discrepancias(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        datos = velas(20)
        descargar(store, datos)
        descargar(store, datos)
        assert not list(tmp_path.rglob("discrepancias"))


class TestRevisionDelProveedor:
    """Cuándo se detecta una revisión, y cuándo no.

    El solape de `missing_ranges` hace que al **ampliar** un histórico se vuelvan a mirar las
    últimas velas ya guardadas, que es donde los proveedores corrigen. Redescargar exactamente el
    mismo rango no pide nada al proveedor (FR-013) y por tanto no puede detectar nada: para eso
    existe la verificación explícita.
    """

    def test_al_ampliar_se_detecta_una_revision_en_la_frontera(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        # La vela 18 cae dentro del solape que se vuelve a pedir al ampliar.
        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        segunda = fetch_history(
            peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera
        )
        assert segunda.discrepancies

    def test_el_historico_local_no_se_toca(self, tmp_path: Path) -> None:
        """FR-026: el backtest de ayer sigue siendo reproducible hoy."""
        store = HistoryStore(tmp_path)
        primera = descargar(store, velas(20))
        antes = primera.path.read_text(encoding="utf-8").splitlines()

        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        fetch_history(peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera)

        despues = primera.path.read_text(encoding="utf-8").splitlines()
        assert despues[:21] == antes[:21], "una vela ya guardada cambio de valor"

    def test_la_version_nueva_se_guarda_aparte(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        segunda = fetch_history(
            peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera
        )
        assert segunda.discrepancy_path is not None
        assert segunda.discrepancy_path.exists()
        assert "555" in segunda.discrepancy_path.read_text(encoding="utf-8")

    def test_el_aviso_identifica_fecha_y_valores(self, tmp_path: Path) -> None:
        """FR-027, SC-011."""
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        segunda = fetch_history(
            peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera
        )
        cierre = next(d for d in segunda.discrepancies if d.field == "close")
        assert cierre.timestamp == velas(40)[18].timestamp
        assert cierre.provider_value == 555.0
        assert cierre.stored_value != 555.0

    def test_aceptarla_no_ocurre_solo(self, tmp_path: Path) -> None:
        """FR-028: adoptar la version nueva es una decision del operador."""
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        fetch_history(peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera)

        guardado = store.load(peticion(40), PROVEEDOR)
        assert guardado is not None
        assert guardado[0].bars[18].close != 555.0

    def test_una_revision_no_bloquea_la_ampliacion(self, tmp_path: Path) -> None:
        """El historico debe poder crecer aunque el proveedor haya revisado algo."""
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        revisado = alterar(velas(40), 18, nuevo_cierre=555.0)
        segunda = fetch_history(
            peticion(40), RecordedProvider(revisado), store, now=AHORA, sleep=sin_espera
        )
        assert segunda.added_count == 20
        assert segunda.discrepancies

    def test_redescargar_el_mismo_rango_no_detecta_nada(self, tmp_path: Path) -> None:
        """Limite honesto del diseno, documentado como test.

        No pedir lo que ya se tiene (FR-013) y detectar revisiones (FR-011) son objetivos
        opuestos. Sin ampliacion no hay peticion, y sin peticion no hay nada que comparar. La
        deteccion completa vive en verify_history, que es explicita a proposito.
        """
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))
        segunda = descargar(store, alterar(velas(20), 5, nuevo_cierre=555.0))

        assert segunda.requests_made == 0
        assert segunda.discrepancies == ()


class TestVerificacionExplicita:
    def test_sin_historico_no_devuelve_nada(self, tmp_path: Path) -> None:
        discrepancias = verify_history(
            peticion(), RecordedProvider(velas(20)), HistoryStore(tmp_path), sleep=sin_espera
        )
        assert discrepancias == ()

    def test_detecta_una_revision(self, tmp_path: Path) -> None:
        store = HistoryStore(tmp_path)
        descargar(store, velas(20))

        discrepancias = verify_history(
            peticion(),
            RecordedProvider(alterar(velas(20), 3, nuevo_cierre=777.0)),
            store,
            sleep=sin_espera,
        )
        assert any(d.provider_value == 777.0 for d in discrepancias)

    def test_no_modifica_nada(self, tmp_path: Path) -> None:
        """FR-029: solo informa."""
        store = HistoryStore(tmp_path)
        primera = descargar(store, velas(20))
        original = primera.path.read_text(encoding="utf-8")

        verify_history(
            peticion(),
            RecordedProvider(alterar(velas(20), 3, nuevo_cierre=777.0)),
            store,
            sleep=sin_espera,
        )
        assert primera.path.read_text(encoding="utf-8") == original

    def test_no_ocurre_durante_una_descarga_normal(self, tmp_path: Path) -> None:
        """FR-029: reverificar en cada uso multiplicaría las peticiones."""
        store = HistoryStore(tmp_path)
        provider = RecordedProvider(velas(20))
        fetch_history(peticion(), provider, store, now=AHORA, sleep=sin_espera)
        tras_primera = provider.calls

        fetch_history(peticion(), provider, store, now=AHORA, sleep=sin_espera)
        assert provider.calls == tras_primera, "la segunda descarga reverificó por su cuenta"
