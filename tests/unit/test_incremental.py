"""T041 — solo se pide lo que falta (US3, SC-005, FR-013).

Los proveedores públicos limitan las peticiones. Sin esto, ampliar un histórico grande resulta
lento o directamente se bloquea.
"""

from __future__ import annotations

from pathlib import Path

from invest_ll.data.bar import Interval
from invest_ll.fetch.providers.recorded import RecordedProvider
from invest_ll.fetch.request import FetchRequest, Market
from invest_ll.fetch.service import fetch_history
from invest_ll.fetch.store import HistoryStore

from ..fixtures.recorded_data import ORIGEN, velas

PASO = Interval.DAY_1.duration
AHORA = ORIGEN + PASO * 1000


def sin_espera(_segundos: float) -> None:
    pass


def peticion(n: int, desde: int = 0) -> FetchRequest:
    return FetchRequest(
        symbol="BTC/USDT",
        interval=Interval.DAY_1,
        start=ORIGEN + PASO * desde,
        end=ORIGEN + PASO * n,
        market=Market.CRYPTO,
    )


def test_la_primera_descarga_pide_el_rango_entero(tmp_path: Path) -> None:
    provider = RecordedProvider(velas(50))
    resultado = fetch_history(
        peticion(50), provider, HistoryStore(tmp_path), now=AHORA, sleep=sin_espera
    )
    assert resultado.requests_made == 1
    assert resultado.added_count == 50


def test_un_rango_ya_cubierto_no_gasta_ninguna_peticion(tmp_path: Path) -> None:
    """SC-005 en su forma más estricta: cero."""
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(50))

    fetch_history(peticion(50), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(50), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.requests_made == 0
    assert segunda.added_count == 0


def test_ampliar_por_la_derecha_pide_solo_la_cola(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(100))

    fetch_history(peticion(50), provider, store, now=AHORA, sleep=sin_espera)
    llamadas_previas = provider.calls

    fetch_history(peticion(100), provider, store, now=AHORA, sleep=sin_espera)
    inicio_pedido = provider.requested_ranges[llamadas_previas][0]

    # 50 velas guardadas menos el solape de 5 que se vuelve a mirar a proposito.
    assert inicio_pedido == ORIGEN + PASO * 45


def test_ampliar_no_vuelve_a_pedir_la_ultima_vela(tmp_path: Path) -> None:
    """El bug que encontraron los tests de merge: la cobertura llega al FIN de la vela.

    Comparar con su marca haría que cada descarga volviera a pedir la última que ya tenía.
    """
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(100))

    fetch_history(peticion(50), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(100), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.added_count == 50, "se recontaron velas que ya estaban"


def test_el_numero_de_velas_nuevas_no_supera_lo_que_faltaba(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(200))

    fetch_history(peticion(80), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(200), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.added_count == 120


def test_ampliar_por_ambos_lados_pide_dos_tramos(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(200))

    fetch_history(peticion(120, desde=50), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(200, desde=0), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.requests_made == 2


def test_el_historico_completo_queda_ordenado(tmp_path: Path) -> None:
    store = HistoryStore(tmp_path)
    provider = RecordedProvider(velas(200))

    fetch_history(peticion(120, desde=50), provider, store, now=AHORA, sleep=sin_espera)
    segunda = fetch_history(peticion(200, desde=0), provider, store, now=AHORA, sleep=sin_espera)

    assert segunda.series is not None
    marcas = [b.timestamp for b in segunda.series.bars]
    assert marcas == sorted(marcas)
    assert len(set(marcas)) == len(marcas)
