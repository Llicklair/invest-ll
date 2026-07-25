"""Universo de activos alineados."""

from __future__ import annotations

from datetime import timedelta

import pytest

from invest_ll.data.bar import Interval
from invest_ll.data.universe import build_universe
from invest_ll.errors import InvalidSeriesError

from ..fixtures.builders import ORIGIN, ramp, series_from_closes

PASO = Interval.DAY_1.duration


def test_alinea_dos_series_identicas_en_fechas() -> None:
    a = series_from_closes(ramp(10), symbol="A")
    b = series_from_closes(ramp(10, start=200.0), symbol="B")
    universo = build_universe([a, b])

    assert len(universo) == 10
    assert universo.symbols == ("A", "B")


def test_solo_conserva_las_fechas_comunes() -> None:
    """Comparar un activo que cotizo con otro que no, no compara nada."""
    a = series_from_closes(ramp(10), symbol="A")
    b = series_from_closes(ramp(6, start=200.0), symbol="B", start=ORIGIN + PASO * 4)
    universo = build_universe([a, b])

    assert len(universo) == 6
    assert universo.timestamps[0] == ORIGIN + PASO * 4


def test_sin_fechas_comunes_se_rechaza() -> None:
    a = series_from_closes(ramp(5), symbol="A")
    b = series_from_closes(ramp(5), symbol="B", start=ORIGIN + PASO * 100)
    with pytest.raises(InvalidSeriesError, match="ninguna fecha"):
        build_universe([a, b])


def test_un_solo_activo_se_rechaza() -> None:
    """Rotar entre uno no es rotar."""
    with pytest.raises(InvalidSeriesError, match="al menos 2"):
        build_universe([series_from_closes(ramp(10), symbol="A")])


def test_activos_repetidos_se_rechazan() -> None:
    a = series_from_closes(ramp(10), symbol="A")
    with pytest.raises(InvalidSeriesError, match="repetidos"):
        build_universe([a, a])


def test_intervalos_distintos_se_rechazan() -> None:
    """Comparar velas diarias con horarias mezclaria escalas de tiempo."""
    a = series_from_closes(ramp(10), symbol="A")
    b = series_from_closes(ramp(10), symbol="B", interval=Interval.HOUR_1)
    with pytest.raises(InvalidSeriesError, match="intervalo"):
        build_universe([a, b])


class TestAccesoADatos:
    def test_devuelve_la_vela_correcta_de_cada_activo(self) -> None:
        a = series_from_closes(ramp(10), symbol="A")
        b = series_from_closes(ramp(10, start=200.0), symbol="B")
        universo = build_universe([a, b])

        assert universo.bar("A", 0).close == 100.0
        assert universo.bar("B", 0).close == 200.0

    def test_los_cierres_hasta_un_indice_no_incluyen_el_futuro(self) -> None:
        """Principio II extendido a varios activos."""
        a = series_from_closes(ramp(10), symbol="A")
        b = series_from_closes(ramp(10, start=200.0), symbol="B")
        universo = build_universe([a, b])

        cierres = universo.closes_until("A", index=3, periods=10)
        assert cierres == (100.0, 101.0, 102.0, 103.0)
        assert max(cierres) == 103.0, "se colo un precio posterior al indice"

    def test_limita_al_numero_de_periodos_pedido(self) -> None:
        a = series_from_closes(ramp(10), symbol="A")
        b = series_from_closes(ramp(10, start=200.0), symbol="B")
        universo = build_universe([a, b])

        assert len(universo.closes_until("A", index=8, periods=3)) == 3

    def test_al_principio_devuelve_lo_que_hay_sin_rellenar(self) -> None:
        a = series_from_closes(ramp(10), symbol="A")
        b = series_from_closes(ramp(10, start=200.0), symbol="B")
        universo = build_universe([a, b])

        assert len(universo.closes_until("A", index=1, periods=50)) == 2

    def test_periodos_no_positivos_se_rechazan(self) -> None:
        a = series_from_closes(ramp(10), symbol="A")
        b = series_from_closes(ramp(10, start=200.0), symbol="B")
        universo = build_universe([a, b])

        with pytest.raises(ValueError, match="positivo"):
            universo.closes_until("A", index=5, periods=0)


def test_las_fechas_quedan_ordenadas() -> None:
    a = series_from_closes(ramp(20), symbol="A")
    b = series_from_closes(ramp(20, start=200.0), symbol="B")
    universo = build_universe([a, b])
    assert list(universo.timestamps) == sorted(universo.timestamps)


def test_todos_los_activos_tienen_el_mismo_numero_de_velas() -> None:
    """Si uno tuviera mas, la rotacion compararia indices desalineados."""
    a = series_from_closes(ramp(10), symbol="A")
    b = series_from_closes(ramp(6, start=200.0), symbol="B", start=ORIGIN + PASO * 4)
    universo = build_universe([a, b])

    longitudes = {len(universo.bars_by_symbol[s]) for s in universo.symbols}
    assert longitudes == {len(universo)}


def test_el_intervalo_se_conserva() -> None:
    a = series_from_closes(ramp(10), symbol="A", interval=Interval.HOUR_1)
    b = series_from_closes(ramp(10, start=200.0), symbol="B", interval=Interval.HOUR_1)
    universo = build_universe([a, b])
    assert universo.interval is Interval.HOUR_1
    assert universo.interval.duration == timedelta(hours=1)
