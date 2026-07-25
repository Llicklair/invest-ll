"""T010 — MarketView: la barrera del Principio II (FR-002..FR-004).

El fichero de test más importante del proyecto. Si estas pruebas pasan pero la barrera no
funciona, todo backtest posterior es ficción.
"""

from __future__ import annotations

import contextlib

import pytest

from invest_ll.engine.view import MarketView
from invest_ll.errors import LookAheadError

from ..fixtures.builders import ramp, series_from_closes


@pytest.fixture
def view() -> MarketView:
    """Serie de 10 velas (100..109) con el cursor en la quinta (índice 4, cierre 104)."""
    return MarketView(series_from_closes(ramp(10)), cursor=4)


def test_current_bar_es_la_del_cursor(view: MarketView) -> None:
    assert view.current_bar.close == 104.0


def test_len_cuenta_solo_lo_visible(view: MarketView) -> None:
    """La serie tiene 10 velas; la estrategia solo puede saber de 5."""
    assert len(view) == 5


def test_history_devuelve_pasado_en_orden_cronologico(view: MarketView) -> None:
    history = view.history(3)
    assert [bar.close for bar in history] == [102.0, 103.0, 104.0]


def test_history_nunca_supera_el_cursor(view: MarketView) -> None:
    for bar in view.history(len(view)):
        assert bar.timestamp <= view.current_timestamp


def test_history_pide_mas_de_lo_disponible_devuelve_lo_que_hay(view: MarketView) -> None:
    """Nunca rellena con datos inventados: devuelve menos, y se nota."""
    history = view.history(100)
    assert len(history) == 5
    assert history[0].close == 100.0


def test_closes_coincide_con_history(view: MarketView) -> None:
    assert list(view.closes(3)) == [102.0, 103.0, 104.0]


def test_bar_at_offset_positivo_mira_atras(view: MarketView) -> None:
    assert view.bar_at(0).close == 104.0
    assert view.bar_at(2).close == 102.0


def test_bar_at_offset_negativo_lanza_lookahead(view: MarketView) -> None:
    """El intento de mirar al futuro falla de forma ruidosa, no devuelve un dato."""
    with pytest.raises(LookAheadError):
        view.bar_at(-1)


def test_bar_at_mas_alla_del_inicio_lanza_indexerror(view: MarketView) -> None:
    """Pedir antes del comienzo de la serie es un error del llamante, no look-ahead."""
    with pytest.raises(IndexError):
        view.bar_at(99)


def test_periodos_no_positivos_se_rechazan(view: MarketView) -> None:
    with pytest.raises(ValueError, match="positivo"):
        view.history(0)
    with pytest.raises(ValueError, match="positivo"):
        view.closes(-1)


def test_view_no_expone_la_serie_completa(view: MarketView) -> None:
    """Ningún atributo público debe dar acceso a los datos futuros.

    No es hermetismo (Python no lo permite): es que la superficie pública no ofrece la vía.
    """
    publicos = [name for name in dir(view) if not name.startswith("_")]
    for name in publicos:
        valor = getattr(view, name)
        assert not hasattr(valor, "bars"), f"'{name}' expone la serie completa"


def test_cursor_fuera_de_rango_se_rechaza() -> None:
    serie = series_from_closes(ramp(10))
    with pytest.raises(IndexError):
        MarketView(serie, cursor=10)
    with pytest.raises(IndexError):
        MarketView(serie, cursor=-1)


def test_dos_vistas_del_mismo_cursor_son_equivalentes() -> None:
    """Base del determinismo (FR-005): la vista no arrastra estado oculto."""
    serie = series_from_closes(ramp(10))
    a, b = MarketView(serie, cursor=4), MarketView(serie, cursor=4)
    assert list(a.closes(5)) == list(b.closes(5))


def test_los_cierres_devueltos_son_de_solo_lectura(view: MarketView) -> None:
    """T039: un slice de numpy es una vista sobre el buffer original.

    Sin protección, una estrategia podría reescribir el histórico que ven las demás. No es
    look-ahead, es peor: rompe el determinismo sin que nada falle de forma visible.
    """
    ventana = view.closes(3)
    with pytest.raises(ValueError, match=r"read-only|writeable"):
        ventana[0] = 999.0


def test_reescribir_no_altera_la_serie_original() -> None:
    serie = series_from_closes(ramp(10))
    original = list(serie.closes)
    vista = MarketView(serie, cursor=5)
    with contextlib.suppress(ValueError):
        vista.closes(3)[0] = 999.0
    assert list(serie.closes) == original
