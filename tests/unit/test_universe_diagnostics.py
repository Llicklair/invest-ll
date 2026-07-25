"""Diagnóstico cuando los activos no se pueden combinar.

Caso real encontrado usando el panel: se eligieron BTC (desde 2017), AAPL (desde 2015), GLD
(desde 2005) y SPY (hasta 2010). No hay ni un día en común, pero el mensaje obligaba a deducirlo
comparando cuatro rangos a ojo.

Un error que no dice qué hacer es medio error.
"""

from __future__ import annotations

import pytest

from invest_ll.data.bar import Interval
from invest_ll.data.universe import build_universe, common_range
from invest_ll.errors import InvalidSeriesError

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

PASO = Interval.DAY_1.duration


def test_el_mensaje_nombra_al_que_empieza_mas_tarde() -> None:
    pronto = series_from_closes(ramp(50), symbol="VIEJO")
    tarde = series_from_closes(ramp(50), symbol="NUEVO", start=ORIGIN + PASO * 200)

    with pytest.raises(InvalidSeriesError, match="NUEVO"):
        build_universe([pronto, tarde])


def test_el_mensaje_nombra_al_que_acaba_antes() -> None:
    pronto = series_from_closes(ramp(50), symbol="VIEJO")
    tarde = series_from_closes(ramp(50), symbol="NUEVO", start=ORIGIN + PASO * 200)

    with pytest.raises(InvalidSeriesError, match="VIEJO"):
        build_universe([pronto, tarde])


def test_el_mensaje_sugiere_que_hacer() -> None:
    """Quitar uno o ampliar su descarga: el operador necesita saber la salida."""
    pronto = series_from_closes(ramp(50), symbol="VIEJO")
    tarde = series_from_closes(ramp(50), symbol="NUEVO", start=ORIGIN + PASO * 200)

    with pytest.raises(InvalidSeriesError, match=r"quita|amplia"):
        build_universe([pronto, tarde])


def test_el_mensaje_es_imprimible_en_consola_windows() -> None:
    pronto = series_from_closes(ramp(50), symbol="VIEJO")
    tarde = series_from_closes(ramp(50), symbol="NUEVO", start=ORIGIN + PASO * 200)

    try:
        build_universe([pronto, tarde])
    except InvalidSeriesError as error:
        str(error).encode("cp1252")


class TestRangoComun:
    def test_dos_series_solapadas_tienen_rango_comun(self) -> None:
        a = series_from_closes(ramp(100), symbol="A")
        b = series_from_closes(ramp(100), symbol="B", start=ORIGIN + PASO * 50)
        inicio, fin, quien_empieza, quien_acaba = common_range([a, b])

        assert inicio == ORIGIN + PASO * 50
        assert quien_empieza == "B"
        assert quien_acaba == "A"
        assert inicio <= fin

    def test_dos_series_disjuntas_dan_rango_invertido(self) -> None:
        """El rango invertido es justo la señal de que no hay solape."""
        a = series_from_closes(ramp(50), symbol="A")
        b = series_from_closes(ramp(50), symbol="B", start=ORIGIN + PASO * 200)
        inicio, fin, _, _ = common_range([a, b])

        assert inicio > fin


def test_activos_que_si_solapan_se_combinan() -> None:
    """El arreglo no puede romper el caso normal."""
    a = series_from_closes(ramp(100), symbol="A")
    b = series_from_closes(ramp(100), symbol="B", start=ORIGIN + PASO * 50)
    universo = build_universe([a, b])
    assert len(universo) == 50
